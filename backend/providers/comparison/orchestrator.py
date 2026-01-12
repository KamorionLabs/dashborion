"""
Comparison Orchestrator Provider.

Handles triggering the comparison orchestrator Step Function
and tracking execution state to prevent duplicate runs.
"""

import os
import json
import time
import boto3
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


# DynamoDB table name
TABLE_NAME = os.environ.get('OPS_DASHBOARD_TABLE', 'ops-dashboard-shared-state')

# Default refresh threshold in seconds (1 hour)
DEFAULT_REFRESH_THRESHOLD_SECONDS = 3600

# Execution timeout for Step Functions
SFN_EXECUTION_TIMEOUT = 120

# TTL for execution tracking records (15 minutes)
EXECUTION_TRACKING_TTL_SECONDS = 900


class ExecutionStatus(Enum):
    """Status of orchestrator execution"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class ExecutionState:
    """Current execution state"""
    status: ExecutionStatus
    execution_arn: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'status': self.status.value,
            'executionArn': self.execution_arn,
            'startedAt': self.started_at,
            'completedAt': self.completed_at,
            'error': self.error,
        }


class ComparisonOrchestratorProvider:
    """
    Manages triggering the comparison orchestrator Step Function
    and tracks execution state to prevent duplicate runs.

    Execution tracking is stored in DynamoDB with format:
    - pk: _execution#{project}
    - sk: comparison:{sourceEnv}:{destEnv}
    - Fields: status, executionArn, startedAt, ttl
    """

    def __init__(
        self,
        table_name: str = None,
        region: str = None,
        account_id: str = None,
        refresh_threshold_seconds: int = DEFAULT_REFRESH_THRESHOLD_SECONDS,
    ):
        """
        Initialize the orchestrator provider.

        Args:
            table_name: DynamoDB table name
            region: AWS region
            account_id: AWS account ID for Step Function ARNs
            refresh_threshold_seconds: Threshold for auto-refresh
        """
        self.table_name = table_name or TABLE_NAME
        self.region = region or os.environ.get('AWS_REGION', 'eu-central-1')
        self.account_id = account_id or os.environ.get('AWS_ACCOUNT_ID')
        self.refresh_threshold_seconds = refresh_threshold_seconds
        self._dynamodb = None
        self._sfn_client = None
        self._table = None

    @property
    def dynamodb(self):
        if self._dynamodb is None:
            self._dynamodb = boto3.resource('dynamodb', region_name=self.region)
        return self._dynamodb

    @property
    def table(self):
        if self._table is None:
            self._table = self.dynamodb.Table(self.table_name)
        return self._table

    @property
    def sfn_client(self):
        if self._sfn_client is None:
            self._sfn_client = boto3.client('stepfunctions', region_name=self.region)
        return self._sfn_client

    def _build_execution_pk(self, project: str) -> str:
        """Build partition key for execution tracking"""
        return f"_execution#{project}"

    def _build_execution_sk(self, source_env: str, dest_env: str) -> str:
        """Build sort key for execution tracking"""
        return f"comparison:{source_env}:{dest_env}"

    def _get_orchestrator_arn(self) -> str:
        """Get the comparison orchestrator Step Function ARN"""
        return f"arn:aws:states:{self.region}:{self.account_id}:stateMachine:ops-dashboard-comparison-orchestrator"

    def get_execution_state(
        self,
        project: str,
        source_env: str,
        dest_env: str,
    ) -> ExecutionState:
        """
        Get current execution state from DynamoDB.
        Also checks Step Function status if execution is running.

        Returns:
            ExecutionState with current status
        """
        pk = self._build_execution_pk(project)
        sk = self._build_execution_sk(source_env, dest_env)

        try:
            response = self.table.get_item(Key={'pk': pk, 'sk': sk})

            if 'Item' not in response:
                return ExecutionState(status=ExecutionStatus.IDLE)

            item = response['Item']
            status_str = item.get('status', 'idle')
            execution_arn = item.get('execution_arn')

            # If status is "running", verify with Step Functions
            if status_str == 'running' and execution_arn:
                try:
                    sfn_response = self.sfn_client.describe_execution(
                        executionArn=execution_arn
                    )
                    sfn_status = sfn_response['status']

                    if sfn_status == 'RUNNING':
                        return ExecutionState(
                            status=ExecutionStatus.RUNNING,
                            execution_arn=execution_arn,
                            started_at=item.get('started_at'),
                        )
                    elif sfn_status == 'SUCCEEDED':
                        # Update DynamoDB with completed status
                        self._update_execution_state(
                            project, source_env, dest_env,
                            ExecutionStatus.SUCCEEDED, execution_arn
                        )
                        return ExecutionState(
                            status=ExecutionStatus.SUCCEEDED,
                            execution_arn=execution_arn,
                            started_at=item.get('started_at'),
                            completed_at=datetime.now(timezone.utc).isoformat(),
                        )
                    else:
                        # FAILED, TIMED_OUT, ABORTED
                        error_msg = sfn_response.get('error', sfn_status)
                        self._update_execution_state(
                            project, source_env, dest_env,
                            ExecutionStatus.FAILED, execution_arn, error_msg
                        )
                        return ExecutionState(
                            status=ExecutionStatus.FAILED,
                            execution_arn=execution_arn,
                            started_at=item.get('started_at'),
                            error=error_msg,
                        )
                except Exception as e:
                    print(f"[ComparisonOrchestrator] Error checking SFN status: {e}")
                    # Assume execution completed if we can't check
                    return ExecutionState(status=ExecutionStatus.IDLE)

            # Return cached status
            return ExecutionState(
                status=ExecutionStatus(status_str) if status_str in [e.value for e in ExecutionStatus] else ExecutionStatus.IDLE,
                execution_arn=execution_arn,
                started_at=item.get('started_at'),
                completed_at=item.get('completed_at'),
                error=item.get('error'),
            )

        except Exception as e:
            print(f"[ComparisonOrchestrator] Error getting execution state: {e}")
            return ExecutionState(status=ExecutionStatus.IDLE)

    def _update_execution_state(
        self,
        project: str,
        source_env: str,
        dest_env: str,
        status: ExecutionStatus,
        execution_arn: str = None,
        error: str = None,
    ):
        """Update execution state in DynamoDB"""
        pk = self._build_execution_pk(project)
        sk = self._build_execution_sk(source_env, dest_env)

        now = datetime.now(timezone.utc)
        ttl = int(now.timestamp()) + EXECUTION_TRACKING_TTL_SECONDS

        item = {
            'pk': pk,
            'sk': sk,
            'status': status.value,
            'updated_at': now.isoformat(),
            'ttl': ttl,
        }

        if execution_arn:
            item['execution_arn'] = execution_arn

        if status == ExecutionStatus.RUNNING:
            item['started_at'] = now.isoformat()
        elif status in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED):
            item['completed_at'] = now.isoformat()

        if error:
            item['error'] = error

        try:
            self.table.put_item(Item=item)
        except Exception as e:
            print(f"[ComparisonOrchestrator] Error updating execution state: {e}")

    def trigger_orchestrator(
        self,
        project: str,
        source_env: str,
        dest_env: str,
        force: bool = False,
        wait: bool = False,
    ) -> Dict[str, Any]:
        """
        Trigger the comparison orchestrator Step Function.

        Prevents duplicate executions by checking current state first.

        Args:
            project: Project name (e.g., 'mro-mi2')
            source_env: Source environment (e.g., 'legacy-staging')
            dest_env: Destination environment (e.g., 'nh-staging')
            force: Force new execution even if one is running
            wait: Wait for execution to complete

        Returns:
            Dict with execution status and details
        """
        # Check current execution state
        current_state = self.get_execution_state(project, source_env, dest_env)

        if current_state.status == ExecutionStatus.RUNNING and not force:
            return {
                'status': 'already_running',
                'message': 'Comparison is already in progress',
                'executionArn': current_state.execution_arn,
                'startedAt': current_state.started_at,
            }

        if not self.account_id:
            return {
                'status': 'error',
                'message': 'AWS_ACCOUNT_ID not configured',
            }

        orchestrator_arn = self._get_orchestrator_arn()

        # Build Step Function input
        sfn_input = {
            'Project': project,
            'SourceEnv': source_env,
            'DestinationEnv': dest_env,
        }

        print(f"[ComparisonOrchestrator] Triggering orchestrator: {sfn_input}")

        try:
            response = self.sfn_client.start_execution(
                stateMachineArn=orchestrator_arn,
                input=json.dumps(sfn_input),
            )
            execution_arn = response['executionArn']
            print(f"[ComparisonOrchestrator] Started execution: {execution_arn}")

            # Update execution state
            self._update_execution_state(
                project, source_env, dest_env,
                ExecutionStatus.RUNNING, execution_arn
            )

            if not wait:
                return {
                    'status': 'started',
                    'message': 'Comparison started',
                    'executionArn': execution_arn,
                    'startedAt': datetime.now(timezone.utc).isoformat(),
                }

            # Wait for completion
            return self._wait_for_completion(
                project, source_env, dest_env, execution_arn
            )

        except Exception as e:
            error_msg = str(e)
            print(f"[ComparisonOrchestrator] Failed to start execution: {e}")

            self._update_execution_state(
                project, source_env, dest_env,
                ExecutionStatus.FAILED, error=error_msg
            )

            return {
                'status': 'error',
                'message': f'Failed to trigger orchestrator: {error_msg}',
            }

    def _wait_for_completion(
        self,
        project: str,
        source_env: str,
        dest_env: str,
        execution_arn: str,
    ) -> Dict[str, Any]:
        """Wait for Step Function execution to complete"""
        start_time = time.time()

        while time.time() - start_time < SFN_EXECUTION_TIMEOUT:
            try:
                response = self.sfn_client.describe_execution(
                    executionArn=execution_arn
                )
                status = response['status']

                if status == 'SUCCEEDED':
                    self._update_execution_state(
                        project, source_env, dest_env,
                        ExecutionStatus.SUCCEEDED, execution_arn
                    )

                    output = json.loads(response.get('output', '{}'))
                    return {
                        'status': 'succeeded',
                        'message': 'Comparison completed',
                        'executionArn': execution_arn,
                        'output': output,
                    }

                elif status in ('FAILED', 'TIMED_OUT', 'ABORTED'):
                    error_msg = response.get('error', status)
                    cause = response.get('cause', '')

                    self._update_execution_state(
                        project, source_env, dest_env,
                        ExecutionStatus.FAILED, execution_arn, error_msg
                    )

                    return {
                        'status': 'failed',
                        'message': f'Comparison failed: {error_msg}',
                        'executionArn': execution_arn,
                        'error': error_msg,
                        'cause': cause,
                    }

                time.sleep(2)

            except Exception as e:
                print(f"[ComparisonOrchestrator] Error checking execution: {e}")
                time.sleep(2)

        # Timeout
        self._update_execution_state(
            project, source_env, dest_env,
            ExecutionStatus.TIMED_OUT, execution_arn, 'Execution timed out'
        )

        return {
            'status': 'timed_out',
            'message': f'Execution timed out after {SFN_EXECUTION_TIMEOUT}s',
            'executionArn': execution_arn,
        }

    def should_auto_refresh(
        self,
        project: str,
        source_env: str,
        dest_env: str,
        last_updated: str = None,
        pending_checks: int = 0,
    ) -> bool:
        """
        Check if comparison data should be auto-refreshed.

        Returns True if:
        - No last_updated timestamp (no data)
        - Data is older than refresh_threshold_seconds
        - There are pending checks (missing data)
        - No execution is currently running
        """
        # Check if execution is running
        current_state = self.get_execution_state(project, source_env, dest_env)
        if current_state.status == ExecutionStatus.RUNNING:
            return False

        # Check if data is stale
        if not last_updated:
            return True

        # Check if there are pending checks (missing data)
        if pending_checks > 0:
            return True

        try:
            if last_updated.endswith('Z'):
                last_updated = last_updated[:-1] + '+00:00'
            last_dt = datetime.fromisoformat(last_updated)

            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            age_seconds = (now - last_dt).total_seconds()

            return age_seconds > self.refresh_threshold_seconds

        except (ValueError, TypeError):
            return True

"""Output formatting utilities for Dashborion CLI"""

import json
import yaml
from typing import Any, Dict, List, Optional, Union
from datetime import datetime


class OutputFormatter:
    """Format output in different formats (table, json, yaml)"""

    def __init__(self, format: str = 'table'):
        self.format = format

    def output(self, data: Any, title: Optional[str] = None, headers: Optional[List[str]] = None):
        """Output data in the configured format"""
        if self.format == 'json':
            self._output_json(data)
        elif self.format == 'yaml':
            self._output_yaml(data)
        else:
            self._output_table(data, title, headers)

    def _output_json(self, data: Any):
        """Output as JSON"""
        print(json.dumps(data, indent=2, default=str))

    def _output_yaml(self, data: Any):
        """Output as YAML"""
        print(yaml.dump(data, default_flow_style=False, allow_unicode=True))

    def _output_table(self, data: Any, title: Optional[str] = None, headers: Optional[List[str]] = None):
        """Output as formatted table"""
        if title:
            print(f"\n{title}")
            print("=" * len(title))

        if isinstance(data, dict):
            self._print_dict_table(data)
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                self._print_list_table(data, headers)
            else:
                for item in data:
                    print(f"  - {item}")
        else:
            print(data)

    def _print_dict_table(self, data: Dict[str, Any], indent: int = 0):
        """Print dictionary as key-value table"""
        max_key_len = max(len(str(k)) for k in data.keys()) if data else 0

        for key, value in data.items():
            key_str = str(key).ljust(max_key_len)
            if isinstance(value, dict):
                print(f"{'  ' * indent}{key_str}:")
                self._print_dict_table(value, indent + 1)
            elif isinstance(value, list):
                if value and isinstance(value[0], dict):
                    print(f"{'  ' * indent}{key_str}:")
                    for item in value:
                        print(f"{'  ' * (indent + 1)}-")
                        self._print_dict_table(item, indent + 2)
                else:
                    print(f"{'  ' * indent}{key_str}: {', '.join(str(v) for v in value)}")
            else:
                print(f"{'  ' * indent}{key_str}: {value}")

    def _print_list_table(self, data: List[Dict], headers: Optional[List[str]] = None):
        """Print list of dicts as table"""
        if not data:
            print("  (no data)")
            return

        # Determine columns
        if headers:
            columns = headers
        else:
            columns = list(data[0].keys())

        # Calculate column widths
        widths = {}
        for col in columns:
            values = [str(row.get(col, ''))[:50] for row in data]
            widths[col] = max(len(col), max(len(v) for v in values) if values else 0)

        # Print header
        header_line = "  " + "  ".join(col.upper().ljust(widths[col]) for col in columns)
        print(header_line)
        print("  " + "  ".join("-" * widths[col] for col in columns))

        # Print rows
        for row in data:
            row_line = "  " + "  ".join(
                str(row.get(col, ''))[:50].ljust(widths[col])
                for col in columns
            )
            print(row_line)


def format_datetime(dt: Union[datetime, str, None]) -> str:
    """Format datetime for display"""
    if dt is None:
        return '-'
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError:
            return dt

    return dt.strftime('%Y-%m-%d %H:%M:%S')


def format_status(status: str) -> str:
    """Format status with color codes (for terminals that support it)"""
    status_lower = status.lower()

    # ANSI color codes
    colors = {
        'running': '\033[92m',      # Green
        'active': '\033[92m',
        'healthy': '\033[92m',
        'succeeded': '\033[92m',
        'pending': '\033[93m',      # Yellow
        'inprogress': '\033[93m',
        'updating': '\033[93m',
        'failed': '\033[91m',       # Red
        'stopped': '\033[91m',
        'unhealthy': '\033[91m',
    }
    reset = '\033[0m'

    color = colors.get(status_lower, '')
    return f"{color}{status}{reset}" if color else status


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"

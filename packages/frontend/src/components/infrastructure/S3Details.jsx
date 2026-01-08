import { HardDrive as Bucket, ExternalLink } from 'lucide-react'

export default function S3Details({ buckets, infrastructure, env }) {
  if (!buckets || buckets.length === 0) {
    return <p className="text-gray-500">No S3 buckets found for this environment</p>
  }

  if (buckets[0]?.error) {
    return <p className="text-red-400">{buckets[0].error}</p>
  }

  return (
    <div className="space-y-4">
      <div className="text-sm text-gray-400 mb-2">
        {buckets.length} bucket{buckets.length > 1 ? 's' : ''} found
      </div>

      {buckets.map((bucket, i) => (
        <div key={i} className="bg-gray-900 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Bucket className="w-4 h-4 text-purple-400" />
              <span className="text-sm font-medium text-gray-300">{bucket.name}</span>
            </div>
            <span className={`text-xs px-2 py-0.5 rounded ${
              bucket.type === 'frontend' ? 'bg-blue-500/20 text-blue-400' :
              bucket.type === 'cms-public' ? 'bg-orange-500/20 text-orange-400' :
              'bg-gray-500/20 text-gray-400'
            }`}>
              {bucket.type}
            </span>
          </div>

          <div className="space-y-2 text-sm">
            {bucket.createdAt && (
              <div className="flex justify-between">
                <span className="text-gray-500">Created</span>
                <span className="text-gray-400">{new Date(bucket.createdAt).toLocaleDateString()}</span>
              </div>
            )}
            {bucket.size && (
              <div className="flex justify-between">
                <span className="text-gray-500">Size</span>
                <span className="text-gray-400">{(bucket.size / 1024 / 1024).toFixed(2)} MB</span>
              </div>
            )}
            {bucket.objectCount && (
              <div className="flex justify-between">
                <span className="text-gray-500">Objects</span>
                <span className="text-gray-400">{bucket.objectCount.toLocaleString()}</span>
              </div>
            )}
          </div>

          {bucket.consoleUrl && (
            <a
              href={bucket.consoleUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 flex items-center justify-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
            >
              <ExternalLink className="w-4 h-4" />
              Open in Console
            </a>
          )}
        </div>
      ))}
    </div>
  )
}

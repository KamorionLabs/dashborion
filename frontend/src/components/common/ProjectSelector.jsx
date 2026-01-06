import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Star, Search, Check } from 'lucide-react'
import { useProjectManager } from '../../ConfigContext'

/**
 * Project Selector Component
 * Displays favorite projects as quick-access tabs and a dropdown for all projects
 */
export default function ProjectSelector() {
  const {
    currentProjectId,
    projectList,
    favoriteProjects,
    selectProject,
    toggleFavorite
  } = useProjectManager()

  const [isOpen, setIsOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const dropdownRef = useRef(null)
  const searchInputRef = useRef(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false)
        setSearchQuery('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      searchInputRef.current.focus()
    }
  }, [isOpen])

  // Get current project
  const currentProject = projectList.find(p => p.id === currentProjectId)

  // Filter projects by search
  const filteredProjects = projectList.filter(project =>
    project.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    project.shortName?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    project.client?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Separate favorites and non-favorites
  const favoriteProjectsList = filteredProjects.filter(p => p.isFavorite)
  const otherProjectsList = filteredProjects.filter(p => !p.isFavorite)

  const handleSelectProject = (projectId) => {
    selectProject(projectId)
    setIsOpen(false)
    setSearchQuery('')
  }

  const handleToggleFavorite = (e, projectId) => {
    e.stopPropagation()
    toggleFavorite(projectId)
  }

  // Only show favorite tabs if there are favorites and more than 1 project
  const showFavoriteTabs = favoriteProjects.length > 0 && projectList.length > 1

  return (
    <div className="flex items-center gap-2">
      {/* Favorite project quick tabs */}
      {showFavoriteTabs && (
        <div className="flex items-center gap-1">
          {projectList
            .filter(p => p.isFavorite)
            .slice(0, 5) // Max 5 favorite tabs
            .map(project => (
              <button
                key={project.id}
                onClick={() => selectProject(project.id)}
                className={`flex items-center gap-1.5 px-2 py-1 rounded text-sm transition-colors ${
                  currentProjectId === project.id
                    ? 'bg-brand-600 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
                style={{
                  borderLeft: `3px solid ${project.color || '#6b7280'}`
                }}
                title={project.name}
              >
                <span className="font-medium">{project.shortName || project.name.slice(0, 2).toUpperCase()}</span>
              </button>
            ))}
        </div>
      )}

      {/* Dropdown for all projects */}
      <div className="relative" ref={dropdownRef}>
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-md transition-colors"
        >
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: currentProject?.color || '#6b7280' }}
          />
          <span className="text-sm font-medium max-w-[150px] truncate">
            {currentProject?.name || 'Select Project'}
          </span>
          <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </button>

        {/* Dropdown menu */}
        {isOpen && (
          <div className="absolute top-full left-0 mt-1 w-72 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden">
            {/* Search input */}
            {projectList.length > 3 && (
              <div className="p-2 border-b border-gray-700">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                  <input
                    ref={searchInputRef}
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search projects..."
                    className="w-full pl-8 pr-3 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-300 placeholder-gray-500 focus:outline-none focus:border-brand-500"
                  />
                </div>
              </div>
            )}

            <div className="max-h-80 overflow-y-auto">
              {/* Favorites section */}
              {favoriteProjectsList.length > 0 && (
                <div>
                  <div className="px-3 py-1.5 text-xs font-medium text-gray-500 uppercase tracking-wide bg-gray-850">
                    Favorites
                  </div>
                  {favoriteProjectsList.map(project => (
                    <ProjectItem
                      key={project.id}
                      project={project}
                      isSelected={currentProjectId === project.id}
                      onSelect={() => handleSelectProject(project.id)}
                      onToggleFavorite={(e) => handleToggleFavorite(e, project.id)}
                    />
                  ))}
                </div>
              )}

              {/* Other projects section */}
              {otherProjectsList.length > 0 && (
                <div>
                  {favoriteProjectsList.length > 0 && (
                    <div className="px-3 py-1.5 text-xs font-medium text-gray-500 uppercase tracking-wide bg-gray-850">
                      All Projects
                    </div>
                  )}
                  {otherProjectsList.map(project => (
                    <ProjectItem
                      key={project.id}
                      project={project}
                      isSelected={currentProjectId === project.id}
                      onSelect={() => handleSelectProject(project.id)}
                      onToggleFavorite={(e) => handleToggleFavorite(e, project.id)}
                    />
                  ))}
                </div>
              )}

              {/* Empty state */}
              {filteredProjects.length === 0 && (
                <div className="px-4 py-8 text-center text-gray-500 text-sm">
                  No projects found
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * Individual project item in the dropdown
 */
function ProjectItem({ project, isSelected, onSelect, onToggleFavorite }) {
  return (
    <button
      onClick={onSelect}
      className={`w-full flex items-center gap-3 px-3 py-2 text-left transition-colors ${
        isSelected
          ? 'bg-brand-600/20 text-brand-400'
          : 'hover:bg-gray-700 text-gray-300'
      }`}
    >
      <div
        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
        style={{ backgroundColor: project.color || '#6b7280' }}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate">{project.name}</span>
          {project.shortName && (
            <span className="text-xs text-gray-500 font-mono">[{project.shortName}]</span>
          )}
        </div>
        {project.client && (
          <div className="text-xs text-gray-500 truncate">{project.client}</div>
        )}
      </div>
      <div className="flex items-center gap-2">
        {isSelected && (
          <Check className="w-4 h-4 text-brand-400" />
        )}
        <button
          onClick={onToggleFavorite}
          className={`p-1 rounded transition-colors ${
            project.isFavorite
              ? 'text-yellow-400 hover:text-yellow-300'
              : 'text-gray-600 hover:text-gray-400'
          }`}
          title={project.isFavorite ? 'Remove from favorites' : 'Add to favorites'}
        >
          <Star className={`w-4 h-4 ${project.isFavorite ? 'fill-current' : ''}`} />
        </button>
      </div>
    </button>
  )
}

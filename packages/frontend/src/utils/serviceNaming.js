export const formatServicePrefix = (serviceNaming, projectId, env) => {
  const template = serviceNaming?.prefix
  if (!template) {
    if (projectId && env) return `${projectId}-${env}-`
    return ''
  }

  if (template.includes('{project}') || template.includes('{env}')) {
    return template
      .replaceAll('{project}', projectId || '')
      .replaceAll('{env}', env || '')
  }

  if (projectId && env && template === projectId) {
    return `${template}-${env}-`
  }

  return template
}

export const stripServiceName = (serviceName, serviceNaming, projectId, env) => {
  if (!serviceName) return ''
  const prefix = formatServicePrefix(serviceNaming, projectId, env)
  if (prefix && serviceName.startsWith(prefix)) {
    return serviceName.slice(prefix.length)
  }
  return serviceName
}

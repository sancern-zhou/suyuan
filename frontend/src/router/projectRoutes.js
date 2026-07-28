export function filterProjectRoutes(routes, hasModule) {
  return routes.filter(route => {
    const required = route.meta?.requiredModule
    return !required || hasModule(required)
  })
}

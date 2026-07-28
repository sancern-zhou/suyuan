export function filterSidebarModules(modules, hasModule) {
  return modules.filter(item => !item.requiredModule || hasModule(item.requiredModule))
}

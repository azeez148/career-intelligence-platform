const roles = [['501-frontend-engineer', 'Frontend Engineer'], ['502-ux-researcher', 'UX Researcher'],
  ['503-support-specialist', 'Support Specialist']];
const list = document.createElement('ul');
for (const [slug, title] of roles) {
  const item = document.createElement('li');
  const link = document.createElement('a');
  link.href = '/careers/jobs/' + slug;
  link.textContent = title;
  item.append(link);
  list.append(item);
}
document.getElementById('root').append(list);

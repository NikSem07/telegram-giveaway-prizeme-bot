import { renderHomePage } from './home/home.js';

let currentPage = null;

function setupNavigation() {
  const items = document.querySelectorAll('.bottom-nav .nav-item');
  items.forEach(item => {
    item.addEventListener('click', () => {
      const page = item.getAttribute('data-page');
      switchPage(page);
    });
  });
}

function switchPage(page) {
  if (!page || page === currentPage) return;
  currentPage = page;

  // active state
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.page === page);
  });

  if (page === 'home') {
    document.body.classList.add('home-page');
    renderHomePage();
    return;
  }

  document.body.classList.remove('home-page');

  // остальные страницы пока вызываем из window (их держим в entry-файле)
  if (page === 'tasks' && window.renderTasksPage) window.renderTasksPage();
  else if (page === 'giveaways' && window.renderGiveawaysPage) window.renderGiveawaysPage();
  else if (page === 'profile' && window.renderProfilePage) window.renderProfilePage();
}

function getCurrentPage() {
  return currentPage;
}

export { setupNavigation, switchPage, getCurrentPage };

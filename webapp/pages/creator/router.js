import { renderHomePage } from './home/home.js';
import { renderServicesPage } from './services/services.js';
import { renderGiveawaysPage } from './giveaways/giveaways.js';
import { renderStatsPage } from './stats/stats.js';

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

  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.page === page);
  });

  document.body.classList.toggle('home-page', page === 'home');

  if (page === 'home') {
    renderHomePage();
    return;
  }
  if (page === 'services') {
    renderServicesPage();
    return;
  }
  if (page === 'giveaways') {
    renderGiveawaysPage();
    return;
  }
  if (page === 'stats') {
    renderStatsPage();
    return;
  }
}

export { setupNavigation, switchPage };

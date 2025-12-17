import { renderHomePage } from './home/home.js';
import { renderTasksPage } from './tasks/tasks.js';
import { renderGiveawaysPage } from './giveaways/giveaways.js';
import { renderProfilePage } from './profile/profile.js';

import { renderCreatorHomePage } from '../creator/home/home.js';

let currentPage = null;

function getCurrentPage() {
  return currentPage;
}

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

  if (page === 'creator-home') {
    renderCreatorHomePage();
    return;
  }

  if (page === 'tasks') {
    renderTasksPage();
    return;
  }

  if (page === 'giveaways') {
    renderGiveawaysPage();
    return;
  }

  if (page === 'profile') {
    renderProfilePage();
    return;
  }
}

export { setupNavigation, switchPage, getCurrentPage };

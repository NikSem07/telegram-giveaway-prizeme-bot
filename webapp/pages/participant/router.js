// pages/participant/router.js

let currentPage = null;

// ====== Навигация по нижнему бару ======

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

  // Активный таб
  document.querySelectorAll('.nav-item').forEach(item => {
    if (item.dataset.page === page) {
        item.classList.add('active');
    } else {
        item.classList.remove('active');
    }
  });

  // Переключение страниц
  if (page === 'home') {
    document.body.classList.add('home-page');
    renderHomePage();
  } else {
    document.body.classList.remove('home-page');
    
    if (page === 'tasks') renderTasksPage();
    else if (page === 'giveaways') renderGiveawaysPage();
    else if (page === 'profile') renderProfilePage();
  }
}
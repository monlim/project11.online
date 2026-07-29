// Project Eleven — hamburger menu toggle (the site's only JavaScript)
document.querySelector('.menu-toggle').addEventListener('click', function () {
  var open = document.body.classList.toggle('nav-open');
  this.setAttribute('aria-expanded', open ? 'true' : 'false');
});


const hamburger = document.querySelector('.hamburger');
const nav = document.querySelector('.nav');

hamburger.addEventListener('click', () => {
  const expanded = hamburger.getAttribute('aria-expanded') === 'true';
  hamburger.setAttribute('aria-expanded', !expanded);
  nav.classList.toggle('show');
});
document.addEventListener("DOMContentLoaded", () => {
    const coursesBtn = document.getElementById("coursesBtn");
    const scholarshipsBtn = document.getElementById("scholarshipsBtn");

    if (coursesBtn) {
        coursesBtn.addEventListener("click", (e) => {
            e.preventDefault();
            window.location.href = "/index3"; // loads index3.html
        });
    }

    if (scholarshipsBtn) {
        scholarshipsBtn.addEventListener("click", (e) => {
            e.preventDefault();
            window.location.href = "/index4"; // loads index4.html
        });
    }
});

document.addEventListener('DOMContentLoaded', () => {
  const year = document.querySelector('[data-year]');
  if (year) year.textContent = new Date().getFullYear();

  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.nav-links');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const isOpen = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(isOpen));
    });
  }

  const form = document.querySelector('#contact-form');
  if (form) {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const name = String(data.get('name') || '').trim();
      const email = String(data.get('email') || '').trim();
      const product = String(data.get('product') || '').trim();
      const message = String(data.get('message') || '').trim();
      const note = document.querySelector('#form-note');
      const recipient = 'YOUR-BUSINESS-EMAIL@example.com'; // Replace with your verified company email.
      const subject = encodeURIComponent(`Product enquiry: ${product}`);
      const body = encodeURIComponent(`Name: ${name}\nEmail: ${email}\nProduct / part: ${product}\n\nMessage:\n${message}`);
      if (note) {
        note.textContent = 'Opening your email app. Replace the placeholder recipient in js/main.js with your company email before launch.';
        note.classList.remove('error');
      }
      window.location.href = `mailto:${recipient}?subject=${subject}&body=${body}`;
    });
  }
});

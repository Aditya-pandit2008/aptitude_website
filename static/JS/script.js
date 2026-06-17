// =============================================
// Enhanced Script for Aptitude Test Website
// =============================================

// Smooth scroll behavior for all links
document.addEventListener('DOMContentLoaded', function() {
  // Smooth scroll for navigation links
  const navLinks = document.querySelectorAll('nav a[href^="#"]');
  navLinks.forEach(link => {
    link.addEventListener('click', function(e) {
      e.preventDefault();
      const targetId = this.getAttribute('href');
      const targetElement = document.querySelector(targetId);
      if (targetElement) {
        targetElement.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });

  // Form validation for login
  const loginForm = document.querySelector('.login-card');
  if (loginForm) {
    const loginBtn = loginForm.querySelector('.login-btn');
    const emailInput = loginForm.querySelector('input[type="email"]');
    const passwordInput = loginForm.querySelector('input[type="password"]');

    loginBtn?.addEventListener('click', async function(e) {
      e.preventDefault();
      if (validateLoginForm(emailInput, passwordInput)) {
        await loginUser(emailInput.value.trim(), passwordInput.value);
      }
    });
  }

  // Form validation for signup
  const signupForm = document.querySelector('.Signup-page');
  if (signupForm) {
    const submitBtn = signupForm.querySelector('button:last-of-type');
    const inputs = signupForm.querySelectorAll('input');

    submitBtn?.addEventListener('click', async function(e) {
      e.preventDefault();
      if (validateSignupForm(inputs)) {
        await signupUser(inputs);
      }
    });
  }

  // Add animation to cards on scroll
  addScrollAnimations();

  // Add hover effects to category cards
  const cards = document.querySelectorAll('.card');
  cards.forEach(card => {
    card.addEventListener('mouseenter', function() {
      this.style.animation = 'bounce 0.6s ease-in-out';
    });
  });

  // Password visibility toggle
  const eyeIcons = document.querySelectorAll('.fa-eye');
  eyeIcons.forEach(icon => {
    icon.addEventListener('click', function() {
      const input = this.parentElement.querySelector('input');
      if (input.type === 'password') {
        input.type = 'text';
        this.classList.remove('fa-eye');
        this.classList.add('fa-eye-slash');
      } else {
        input.type = 'password';
        this.classList.remove('fa-eye-slash');
        this.classList.add('fa-eye');
      }
    });
  });

  // Mobile menu toggle (if hamburger menu exists)
  const hamburger = document.querySelector('.hamburger');
  const navMenu = document.querySelector('nav');
  if (hamburger) {
    hamburger.addEventListener('click', function() {
      navMenu?.classList.toggle('active');
      hamburger.classList.toggle('active');
    });
  }

  // Add active state to current navigation item
  updateActiveNavLink();
});

// Form validation functions
function validateLoginForm(emailInput, passwordInput) {
  const email = emailInput?.value.trim() || '';
  const password = passwordInput?.value.trim() || '';
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  if (!email) {
    showNotification('Please enter your email', 'error');
    return false;
  }

  if (!emailRegex.test(email)) {
    showNotification('Please enter a valid email', 'error');
    return false;
  }

  if (!password) {
    showNotification('Please enter your password', 'error');
    return false;
  }

  if (password.length < 8) {
    showNotification('Password must be at least 8 characters', 'error');
    return false;
  }

  return true;
}

function validateSignupForm(inputs) {
  const values = Array.from(inputs).map(input => input.value.trim());
  
  if (values.some(val => !val)) {
    showNotification('Please fill all fields', 'error');
    return false;
  }

  const email = values[1];
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  
  if (!emailRegex.test(email)) {
    showNotification('Please enter a valid email', 'error');
    return false;
  }

  const password = values[2];
  if (password.length < 8) {
    showNotification('Password must be at least 8 characters', 'error');
    return false;
  }

  const confirmPassword = values[3];
  if (password !== confirmPassword) {
    showNotification('Passwords do not match', 'error');
    return false;
  }

  return true;
}

async function loginUser(email, password) {
  try {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    const data = await response.json();
    if (!response.ok) {
      showNotification(data.error || formatApiErrors(data.errors) || 'Login failed', 'error');
      return;
    }

    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    showNotification('Login successful!', 'success');
    window.location.href = '/Dashboard';
  } catch (error) {
    showNotification('Unable to connect to the server', 'error');
  }
}

async function signupUser(inputs) {
  const values = Array.from(inputs).map(input => input.value.trim());
  const [username, email, password] = values;

  try {
    const response = await fetch('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password })
    });

    const data = await response.json();
    if (!response.ok) {
      showNotification(data.error || formatApiErrors(data.errors) || 'Sign up failed', 'error');
      return;
    }

    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    showNotification('Account created successfully!', 'success');
    window.location.href = '/Dashboard';
  } catch (error) {
    showNotification('Unable to connect to the server', 'error');
  }
}

function formatApiErrors(errors) {
  return Array.isArray(errors) ? errors.join(' ') : '';
}

// Notification system
function showNotification(message, type = 'info') {
  const notification = document.createElement('div');
  notification.className = `notification notification-${type}`;
  notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 15px 20px;
    background: ${type === 'success' ? '#4CAF50' : type === 'error' ? '#f44336' : '#2196F3'};
    color: white;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    font-size: 14px;
    font-weight: 500;
    z-index: 10000;
    animation: slideInRight 0.3s ease-out;
  `;
  notification.textContent = message;

  document.body.appendChild(notification);

  setTimeout(() => {
    notification.style.animation = 'slideOutRight 0.3s ease-in';
    setTimeout(() => notification.remove(), 300);
  }, 3000);
}

// Scroll animations
function addScrollAnimations() {
  const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
  };

  const observer = new IntersectionObserver(function(entries) {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
      }
    });
  }, observerOptions);

  const elementsToObserve = document.querySelectorAll('.feature, .card, .feature-box');
  elementsToObserve.forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(el);
  });
}

// Update active navigation link
function updateActiveNavLink() {
  const currentLocation = location.pathname;
  const navLinks = document.querySelectorAll('nav a');

  navLinks.forEach(link => {
    const href = link.getAttribute('href');
    if (href && currentLocation.includes(href.replace(/\//g, ''))) {
      link.style.color = '#9b63af';
      link.style.fontWeight = 'bold';
    }
  });
}

// Add keyframe animations to document
const style = document.createElement('style');
style.textContent = `
  @keyframes slideInRight {
    from {
      opacity: 0;
      transform: translateX(30px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  @keyframes slideOutRight {
    from {
      opacity: 1;
      transform: translateX(0);
    }
    to {
      opacity: 0;
      transform: translateX(30px);
    }
  }

  @keyframes bounce {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-10px); }
  }

  @keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-8px); }
  }
`;
document.head.appendChild(style);

// Debounce function for performance
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Handle window resize for responsive behavior
window.addEventListener('resize', debounce(function() {
  console.log('Window resized');
}, 250));

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
  // Alt + S to focus search (if search exists)
  if (e.altKey && e.key === 's') {
    e.preventDefault();
    const searchInput = document.querySelector('input[type="search"]');
    if (searchInput) searchInput.focus();
  }
});

// Load animations
window.addEventListener('load', function() {
  document.body.classList.add('loaded');
  addScrollAnimations();
});

console.log('✨ Aptitude Test Website Enhanced Script Loaded Successfully!');

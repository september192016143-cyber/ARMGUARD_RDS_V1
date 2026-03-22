// Keyboard shortcuts
// Alt + T → Transaction page
/**
 * hot_key.js — Global keyboard shortcuts for ArmGuard RDS
 * Extracted from base.html to comply with CSP script-src 'self'
 * Currently
document.addEventListener("keydown", function(event) {
    // Alt + T → Transaction page
    if (event.altKey && event.key.toLowerCase() === "t") {
        event.preventDefault(); // prevent browser default
        window.location.href = "/transactions/"; 
        // Replace with {% url 'transactions' %} if you want Django to resolve the route
    }
});

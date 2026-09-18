// Funkce pro zobrazení/skrytí a správné pozicování popup okna
function toggleAuthPopup(popupId, buttonElement) {
    var popup = document.getElementById(popupId);
    if (!popup) return;

    if (popup.style.display === 'block') {
        popup.style.display = 'none';
    } else {
        // Zavřeme případně druhý popup, kdyby byl otevřený
        document.querySelectorAll('.auth-popup').forEach(p => p.style.display = 'none');

        // TRIK: Přesuneme popup přímo do body, aby se vytrhl z vlivu rodičovských prvků
        if (popup.parentElement !== document.body) {
            document.body.appendChild(popup);
        }

        // Zjistíme pozici tlačítka na obrazovce
        var rect = buttonElement.getBoundingClientRect();

        // Nastavíme absolutní fixní pozici na úrovni celé obrazovky
        popup.style.position = 'fixed';
        popup.style.top = (rect.bottom + 6) + 'px';
        popup.style.right = (window.innerWidth - rect.right) + 'px';
        popup.style.left = 'auto';
        popup.style.zIndex = '999999';

        popup.style.display = 'block';
    }
}

// Univerzální správce pro zavírání auth okének při kliknutí mimo
document.addEventListener('click', function(event) {
    var logoutPopup = document.getElementById('logout-form-popup');
    var logoutTrigger = document.getElementById('logout-trigger-container');
    if (logoutPopup && logoutPopup.style.display === 'block') {
        var isInsideLogout = logoutPopup.contains(event.target) || (logoutTrigger && logoutTrigger.contains(event.target));
        if (!isInsideLogout) {
            logoutPopup.style.display = 'none';
        }
    }

    var loginPopup = document.getElementById('login-form-popup');
    var loginTrigger = document.getElementById('login-trigger-container');
    if (loginPopup && loginPopup.style.display === 'block') {
        var isInsideLogin = loginPopup.contains(event.target) || (loginTrigger && loginTrigger.contains(event.target));
        if (!isInsideLogin) {
            loginPopup.style.display = 'none';
        }
    }
});

// Automatické zavření okének při scrollování stránky
window.addEventListener('scroll', function() {
    var logoutPopup = document.getElementById('logout-form-popup');
    var loginPopup = document.getElementById('login-form-popup');

    if (logoutPopup && logoutPopup.style.display === 'block') {
        logoutPopup.style.display = 'none';
    }
    if (loginPopup && loginPopup.style.display === 'block') {
        loginPopup.style.display = 'none';
    }
}, { passive: true });
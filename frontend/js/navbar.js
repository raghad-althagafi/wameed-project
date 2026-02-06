
// this class handles rendering and updating the navigation bar
class Navbar {
    constructor() {
        // get current user data from localStorage (if exists)
        this.user = this.getUser();

        // initialize the navbar when the class is created
        this.init();
    }

    // retrieve user data from localStorage
    getUser() {
        const userJson = localStorage.getItem('currentUser');
        return userJson ? JSON.parse(userJson) : null;
    }

    // logout the user
    logout() {
        localStorage.removeItem('currentUser');
        window.location.href = '../pages/home-page.html';
    }

    // generate the HTML structure of the navbar
    getNavbarHTML() {

        // buttons 
        const authButtons = this.user ? `
            <div class="nav-buttons logged-in">
                <!-- Welcome message shown when user is logged in -->
                <a href="../pages/Profile.html" class="welcome-link">
                <img src="../assets/images/user-icon.svg" alt="Profile"
                    class="navbar-user-icon">
                <span class="welcome-text">أهلاً ${this.user.name}</span>
            </a>

                <!-- Logout button -->
                <button class="main-button btn-logout" onclick="navbar.logout()">تسجيل الخروج</button>
            </div>
        ` : `
            <div class="nav-buttons">
                <!-- Login button -->
                <a href="sign-in.html">
                    <button class="main-button btn-login">تسجيل الدخول</button>
                </a>

                <!-- Signup button -->
                <a href="sign-up.html">
                    <button class="main-button btn-signup">إنشاء حساب</button>
                </a>
            </div>
        `;

        // full navbar 
        return `
            <nav class="navbar">
                <div class="nav-container">
                    <div class="nav-content">

                        <!-- Navbar logo -->
                        <img src="../assets/images/wameed logo Bar.svg" alt="Logo">

                        <!-- Navigation links -->
                        <ul class="nav-links">
                            <li><a href="../pages/home-page.html" class="nav-link">الصفحة الرئيسية</a></li>
                            <li><a href="../pages/PredictedFires.html" class="nav-link">التنبؤ بالحرائق</a></li>
                            <li><a href="../pages/DetectedFires.html" class="nav-link">رصد الحرائق</a></li>
                            <li><a href="../pages/home-page.html#about" class="nav-link">من نحن</a></li>
                        </ul>

                        <!-- Authentication buttons section -->
                        ${authButtons}

                    </div>
                </div>
            </nav>
        `;
    }

    // put the navbar into the page
    init() {
        const container = document.getElementById('navbar-container');

        if (container) {
            container.innerHTML = this.getNavbarHTML();
            this.setActiveLink();
        }
    }

    // Highlight the active navigation link
    // Based on the current page URL
    setActiveLink() {
        const currentPage =
            window.location.pathname.split('/').pop() || 'home-page.html';

        document.querySelectorAll('.nav-link').forEach(link => {
            const linkPage = link.getAttribute('href').split('/').pop();

            if (linkPage === currentPage) {
                link.classList.add('active');
            }
        });
    }  

}

// global navbar instance
let navbar;

// initialize navbar after the DOM is fully loaded
document.addEventListener('DOMContentLoaded', () => {
    navbar = new Navbar();
});

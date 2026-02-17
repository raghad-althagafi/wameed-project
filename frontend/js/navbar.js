//class for handles rendering and updating the navigation bar
class Navbar {
    constructor() {
        //get current user data from localStorage 
        this.user = this.getUser();

        //initialize the navbar
        this.init();
    }

    //retrieve user data from localStorage
    getUser() {
        const userJson = localStorage.getItem('currentUser');
        return userJson ? JSON.parse(userJson) : null;
    }

    // logout the user
    logout() {
        localStorage.removeItem('currentUser');
        window.location.href = '/'; // ✅ Flask route for home
    }

    // generate the HTML structure of the navbar
    getNavbarHTML() {

        // buttons 
        const authButtons = this.user ? `
            <!-- when the user is logged in -->
            <div class="nav-buttons logged-in">
                <!-- welcome message shown when user is logged in -->
                <a href="/profile" class="welcome-link">  <!-- ✅ -->
                    <img src="/assets/images/user-icon.svg" alt="Profile" class="navbar-user-icon"> <!-- ✅ -->
                    <span class="welcome-text">أهلاً ${this.user.name}</span>
                </a>

                <!-- logout button -->
                <button class="main-button btn-login" onclick="navbar.logout()">تسجيل الخروج</button>
            </div>
        ` : `
            <!-- when the user is not loged in -->
            <div class="nav-buttons">
                <!-- login button -->
                <a href="/sign-in"> <!-- ✅ -->
                    <button class="main-button btn-login">تسجيل الدخول</button>
                </a>

                <!-- signup button -->
                <a href="/sign-up"> <!-- ✅ -->
                    <button class="main-button btn-signup">إنشاء حساب</button>
                </a>
            </div>
        `;

        //return the full navbar 
        return `
            <nav class="navbar">
                <div class="nav-container">
                    <div class="nav-content">

                        <!-- website logo -->
                        <img src="/assets/images/wameed logo Bar.svg" alt="Logo"> <!-- ✅ -->

                        <!-- navigation links -->
                        <ul class="nav-links">
                            <li><a href="/" class="nav-link">الصفحة الرئيسية</a></li> <!-- ✅ -->
                            <li><a href="/predicted" class="nav-link">التنبؤ بالحرائق</a></li> <!-- ✅ -->
                            <li><a href="/detected" class="nav-link">رصد الحرائق</a></li> <!-- ✅ -->
                            <li><a href="/#about" class="nav-link no-active">من نحن</a></li> <!-- ✅ -->
                        </ul>

                        <!-- login/ logout buttons section -->
                        ${authButtons}

                    </div>
                </div>
            </nav>
        `;
    }

    //put the navbar into the page
    init() {
        const container = document.getElementById('navbar-container');

        if (container) {
            container.innerHTML = this.getNavbarHTML();
            this.setActiveLink();
        }
    }

    //highlight the active navbar link
    setActiveLink() {
        const currentPath = window.location.pathname;

        document.querySelectorAll('.nav-link').forEach(link => {
            // عشان زر من نحن ما يتفعل
            if (link.classList.contains('no-active')) return;

            const linkPath = link.getAttribute('href');

            if (linkPath === currentPath) {
                link.classList.add('active');
            }
        });
    }

}

//global navbar instance
let navbar;

document.addEventListener('DOMContentLoaded', () => {
    navbar = new Navbar();
});

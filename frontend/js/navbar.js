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
        return userJson ? JSON.parse(userJson) : null; //if the user exists conver JSON to object, otherwise return null
    }

    // logout the user
    logout() {
        localStorage.removeItem('currentUser'); //remove the user data from the localStorage
        window.location.href = '../pages/home-page.html'; //redirect to homepage after logout
    }

    // generate the HTML structure of the navbar
    getNavbarHTML() {

        // buttons 
        const authButtons = this.user ? `
            <!-- when the user is logged in -->
            <div class="nav-buttons logged-in">
                <!-- welcome message shown when user is logged in -->
                <a href="../pages/Profile.html" class="welcome-link">
                    <img src="../assets/images/user-icon.svg" alt="Profile" class="navbar-user-icon">
                    <span class="welcome-text">أهلاً ${this.user.name}</span>
                </a>

                <!-- logout button -->
                <button class="main-button btn-login" onclick="navbar.logout()">تسجيل الخروج</button>
            </div>
        ` : `
            <!-- when the user is not loged in -->
            <div class="nav-buttons">
                <!-- login button -->
                <a href="sign-in.html">
                    <button class="main-button btn-login">تسجيل الدخول</button>
                </a>

                <!-- signup button -->
                <a href="sign-up.html">
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
                        <img src="../assets/images/wameed logo Bar.svg" alt="Logo">

                        <!-- navigation links -->
                        <ul class="nav-links">
                            <li><a href="../pages/home-page.html" class="nav-link">الصفحة الرئيسية</a></li>
                            <li><a href="../pages/PredictedFires.html" class="nav-link">التنبؤ بالحرائق</a></li>
                            <li><a href="../pages/DetectedFires.html" class="nav-link">رصد الحرائق</a></li>
                            <li><a href="../pages/home-page.html#about" class="nav-link">من نحن</a></li>
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
        //where the navbar should appear
        const container = document.getElementById('navbar-container');

        //insert the navbaar in the page if the container exists
        if (container) {
            container.innerHTML = this.getNavbarHTML();
            this.setActiveLink(); //highlight the active page links
        }
    }

    //highlight the active navbar link
    setActiveLink() {
        //get the current page name from the url
        const currentPage =
            window.location.pathname.split('/').pop() || 'home-page.html';

        //loop through all navbar links
        document.querySelectorAll('.nav-link').forEach(link => {
            const linkPage = link.getAttribute('href').split('/').pop(); //get page filename

            //add active class if the link matches the current page
            if (linkPage === currentPage) {
                link.classList.add('active');
            }
        });
    }  

}

//global navbar instance
let navbar;

//create the navbar object when the page finishes loading
document.addEventListener('DOMContentLoaded', () => {
    navbar = new Navbar();
});

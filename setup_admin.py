import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dashboard.settings')
django.setup()

from django.contrib.auth.models import User
from marketing.models import UserProfile

def setup_admin():
    """Setup or update admin user"""
    
    admin_username = 'admin'
    admin_email = 'admin@netiq.com'
    admin_password = 'Admin123!'
    
    # Check if admin user exists
    if User.objects.filter(username=admin_username).exists():
        print(f"Admin user '{admin_username}' already exists. Updating...")
        user = User.objects.get(username=admin_username)
        user.is_staff = True
        user.is_superuser = True
        user.email = admin_email
        user.set_password(admin_password)
        user.save()
        print(f"✅ Updated existing admin user")
    else:
        print(f"Creating new admin user...")
        user = User.objects.create_user(
            username=admin_username,
            email=admin_email,
            password=admin_password,
            first_name='Admin',
            last_name='User'
        )
        user.is_staff = True
        user.is_superuser = True
        user.save()
        print(f"✅ Created new admin user")
    
    # Create or update profile
    profile, created = UserProfile.objects.get_or_create(user=user)
    profile.designation = 'Executive'
    profile.department = 'IT Administration'
    profile.employee_id = 'ADMIN001'
    profile.region = 'Head Office'
    profile.phone = '0300-1234567'
    profile.bio = 'System Administrator'
    profile.save()
    
    if created:
        print(f"✅ Created profile for {user.username}")
    else:
        print(f"✅ Updated profile for {user.username}")
    
    print("\n" + "="*50)
    print("ADMIN LOGIN CREDENTIALS")
    print("="*50)
    print(f"Username: {user.username}")
    print(f"Password: {admin_password}")
    print(f"Email: {user.email}")
    print(f"Is Staff: {user.is_staff}")
    print(f"Is Superuser: {user.is_superuser}")
    print("="*50)
    print("\nAdmin Login URL: http://127.0.0.1:8000/admin-panel/login/")
    print("Regular Login URL: http://127.0.0.1:8000/")

if __name__ == "__main__":
    setup_admin()
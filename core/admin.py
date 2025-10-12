from django.contrib import admin
from .models import SiteSettings, Contact, SiteImage


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Admin for site settings"""

    fieldsets = (
        ('Basic Information', {
            'fields': ('site_name', 'site_description', 'logo')
        }),
        ('Contact Information', {
            'fields': ('contact_email', 'contact_phone', 'contact_address')
        }),
        ('Social Media', {
            'fields': ('facebook_url', 'instagram_url', 'linkedin_url', 'twitter_url')
        }),
        ('SEO', {
            'fields': ('meta_keywords', 'google_analytics_id')
        }),
        ('Maintenance Mode', {
            'fields': ('maintenance_mode',),
            'description': 'Enable maintenance mode to show a maintenance page to all visitors. Staff users will still have access to the site.',
            'classes': ('collapse',)
        }),
    )

    list_display = ('site_name', 'maintenance_mode_status')
    list_display_links = ('site_name',)

    def maintenance_mode_status(self, obj):
        """Display maintenance mode status with icon"""
        if obj.maintenance_mode:
            return '🔧 Active'
        return '✓ Normal'
    maintenance_mode_status.short_description = 'Status'

    def has_add_permission(self, request):
        # Only allow one instance
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion
        return False


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    """Admin for contact submissions"""

    list_display = ('name', 'email', 'subject', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'email', 'subject', 'message')
    readonly_fields = ('name', 'email', 'subject', 'message', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(SiteImage)
class SiteImageAdmin(admin.ModelAdmin):
    """Admin for site images"""

    list_display = ('title', 'key', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('title', 'key', 'alt_text')
    prepopulated_fields = {'key': ('title',)}

from django.db import models
from django.core.cache import cache


class SiteSettings(models.Model):
    """Singleton model for storing website settings"""

    site_name = models.CharField("Site Name", max_length=100, default="Get Algarve")
    site_description = models.CharField("Site Description", max_length=255, blank=True)
    logo = models.ImageField("Logo", upload_to='site_images/', blank=True, null=True)

    # Contact Information
    contact_email = models.EmailField("Contact Email", default="geral@portugalwebdesign.pt")
    contact_phone = models.CharField("Contact Phone", max_length=20, default="+351967764290")
    contact_address = models.TextField("Address", blank=True, default='Rua do Indico Edf Altis R/c\r\nc')

    # Social Media Links
    facebook_url = models.URLField("Facebook URL", blank=True, default="")
    instagram_url = models.URLField("Instagram URL", blank=True, default="")
    linkedin_url = models.URLField("LinkedIn URL", blank=True, default="")
    twitter_url = models.URLField("Twitter URL", blank=True, default="")

    # SEO Fields
    meta_keywords = models.CharField("Meta Keywords", max_length=255, blank=True)
    google_analytics_id = models.CharField("Google Analytics ID", max_length=50, blank=True)

    # Misc
    maintenance_mode = models.BooleanField("Maintenance Mode", default=False)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return self.site_name

    @classmethod
    def load(cls):
        """Load site settings from cache or database"""
        obj = cache.get('site_settings')
        if obj is None:
            obj, created = cls.objects.get_or_create(pk=1)
            cache.set('site_settings', obj, 60 * 60)  # Cache for 1 hour
        return obj

    def save(self, *args, **kwargs):
        """Override save to clear cache"""
        super().save(*args, **kwargs)
        cache.delete('site_settings')


class Contact(models.Model):
    """Model to store contact form submissions"""

    name = models.CharField("Name", max_length=100)
    email = models.EmailField("Email")
    subject = models.CharField("Subject", max_length=200)
    message = models.TextField("Message")
    created_at = models.DateTimeField("Created At", auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Contact Submission"
        verbose_name_plural = "Contact Submissions"

    def __str__(self):
        return f"{self.name} - {self.subject}"


class SiteImage(models.Model):
    """Model for managing images used in templates"""

    title = models.CharField('Title', max_length=100)
    key = models.SlugField('Key', unique=True, help_text='Unique identifier to reference this image in templates')
    image = models.ImageField('Image', upload_to='site_images/')
    alt_text = models.CharField('Alt text', max_length=200, blank=True)
    is_active = models.BooleanField('Active', default=True)

    class Meta:
        verbose_name = 'Site Image'
        verbose_name_plural = 'Site Images'

    def __str__(self):
        return self.title

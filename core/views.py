from django.views.generic import TemplateView, FormView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.translation import get_language
from .forms import ContactForm
from .models import Contact

class HomeView(TemplateView):
    """Home page view"""

    def get_template_names(self):
        lang = get_language()
        return [f'{lang}/core/home.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page'] = 'home'
        return context


class AboutView(TemplateView):
    """About page view"""

    def get_template_names(self):
        lang = get_language()
        return [f'{lang}/core/about.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page'] = 'about'
        return context


class ContactView(FormView):
    """Contact page view with form"""
    form_class = ContactForm
    success_url = reverse_lazy('core:contact')

    def get_template_names(self):
        lang = get_language()
        return [f'{lang}/core/contact.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page'] = 'contact'
        return context

    def form_valid(self, form):
        # Save to database
        Contact.objects.create(
            name=form.cleaned_data['name'],
            email=form.cleaned_data['email'],
            subject=form.cleaned_data['subject'],
            message=form.cleaned_data['message'],
        )
        messages.success(self.request, 'Thank you for your message. We will get back to you soon!')
        return super().form_valid(form)


class PrivacyPolicyView(TemplateView):
    """Privacy policy page view"""

    def get_template_names(self):
        lang = get_language()
        return [f'{lang}/core/privacy_policy.html']


class CookiePolicyView(TemplateView):
    """Cookie policy page view"""

    def get_template_names(self):
        lang = get_language()
        return [f'{lang}/core/cookie_policy.html']

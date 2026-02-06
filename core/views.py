from django.views.generic import TemplateView, FormView
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.http import Http404
from .forms import ContactForm
from .models import Contact, Page


class PageView(TemplateView):
    """Dynamic page view that renders pages from the Page model"""
    template_name = 'core/page.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get the page slug from URL or default to 'home' for root path
        page_slug = kwargs.get('slug', 'home')

        # Get current language
        from django.utils.translation import get_language
        current_lang = get_language()

        # Get the page object - search by language-specific slug
        page_obj = None
        try:
            for page in Page.objects.filter(is_active=True):
                if page.get_slug(current_lang) == page_slug:
                    page_obj = page
                    break

            if not page_obj:
                raise Page.DoesNotExist

        except Page.DoesNotExist:
            raise Http404(f"Page '{page_slug}' not found for language '{current_lang}'")

        context['page_obj'] = page_obj
        context['page'] = page_slug

        # Render page HTML content with translations
        language = current_lang or 'pt'

        if page_obj.html_content:
            from django.template import Template, Context
            translations = (page_obj.content or {}).get('translations', {})
            trans = translations.get(language, translations.get('pt', {}))

            template = Template(page_obj.html_content)
            render_context = Context({
                'trans': trans,
                'LANGUAGE_CODE': language,
                'page': page_obj,
                **context,
            })
            context['page_content'] = template.render(render_context)
        else:
            context['page_content'] = ''

        # Enable edit mode for staff users with ?edit=true
        context['edit_mode'] = (
            self.request.user.is_staff and self.request.GET.get('edit') == 'true'
        )

        return context


class ContactFormView(FormView):
    """Contact form submission handler"""
    form_class = ContactForm

    def get_success_url(self):
        # Redirect back to the contact page
        return reverse_lazy('core:page', kwargs={'slug': 'contact'})

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

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)

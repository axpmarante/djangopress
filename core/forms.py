from django import forms


class ContactForm(forms.Form):
    """Contact form"""

    name = forms.CharField(
        max_length=100,
        label="Your Name",
        widget=forms.TextInput(attrs={'class': 'form-input'})
    )
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={'class': 'form-input'})
    )
    subject = forms.CharField(
        max_length=200,
        label="Subject",
        widget=forms.TextInput(attrs={'class': 'form-input'})
    )
    message = forms.CharField(
        label="Message",
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 5})
    )
    consent = forms.BooleanField(
        label="I consent to having this website store my submitted information",
        required=True
    )

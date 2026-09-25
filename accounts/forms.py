from django import forms

from .models import CustomUser

INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 bg-white px-4 py-3.5 "
    "outline-none transition placeholder:text-slate-300 "
    "focus:border-ink focus:ring-4 focus:ring-ink/10"
)


class ProfilePreferencesForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ("first_name", "last_name", "email", "timezone")
        widgets = {
            "first_name": forms.TextInput(attrs={"placeholder": "First name", "class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"placeholder": "Last name", "class": INPUT_CLASS}),
            "email": forms.EmailInput(attrs={"placeholder": "you@example.com", "class": INPUT_CLASS}),
            "timezone": forms.TextInput(attrs={"placeholder": "Europe/Lisbon", "class": INPUT_CLASS}),
        }
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ProfilePreferencesForm


@login_required
def settings_page(request):
    form = ProfilePreferencesForm(request.POST or None, instance=request.user)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile preferences were saved.")
        return redirect("accounts_web:settings")

    return render(request, "accounts/settings.html", {"form": form})
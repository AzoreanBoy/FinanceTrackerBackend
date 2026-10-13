const sidebar = document.querySelector("#sidebar");
const backdrop = document.querySelector("#sidebar-backdrop");
const sidebarTrigger = document.querySelector("[data-sidebar-open]");
const sidebarClose = document.querySelector("[data-sidebar-close]");
const preferenceKey = "ledger-preferences";
let sidebarOpen = false;

const getPreferences = () => {
  try {
    return JSON.parse(localStorage.getItem(preferenceKey)) || {};
  } catch {
    return {};
  }
};

const preferences = getPreferences();

const savePreferences = () => {
  localStorage.setItem(preferenceKey, JSON.stringify(preferences));
};

const applyPreferences = () => {
  document.documentElement.dataset.accent = preferences.accent || "sunset";
  document.documentElement.dataset.density = preferences.compact ? "compact" : "comfortable";
  document.documentElement.classList.toggle("reduced-motion", Boolean(preferences.reducedMotion));

  document.querySelectorAll("[data-accent-choice]").forEach((button) => {
    const selected = button.dataset.accentChoice === (preferences.accent || "sunset");
    button.setAttribute("aria-pressed", selected);
    button.classList.toggle("ring-2", selected);
    button.classList.toggle("ring-offset-2", selected);
    button.classList.toggle("ring-ink", selected);
  });

  document.querySelectorAll("[data-preference-toggle]").forEach((button) => {
    const enabled = Boolean(preferences[button.dataset.preferenceToggle]);
    button.setAttribute("aria-pressed", enabled);
    button.classList.toggle("bg-ink", enabled);
    button.classList.toggle("bg-slate-200", !enabled);
    button.firstElementChild?.classList.toggle("translate-x-5", enabled);
  });
};

const toggleSidebar = (open) => {
  if (!sidebar) return;
  sidebarOpen = open;
  sidebar?.classList.toggle("-translate-x-full", !open);
  backdrop?.classList.toggle("hidden", !open);
  sidebarTrigger?.setAttribute("aria-expanded", String(open));
  document.body.classList.toggle("overflow-hidden", open && window.matchMedia("(max-width: 1023px)").matches);
  if (open) sidebarClose?.focus();
  else if (window.matchMedia("(max-width: 1023px)").matches) sidebarTrigger?.focus();
};

sidebarTrigger?.addEventListener("click", () => toggleSidebar(true));
sidebarClose?.addEventListener("click", () => toggleSidebar(false));
backdrop?.addEventListener("click", () => toggleSidebar(false));
sidebar?.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => {
    if (window.matchMedia("(max-width: 1023px)").matches) toggleSidebar(false);
  });
});
window.addEventListener("resize", () => {
  if (!window.matchMedia("(max-width: 1023px)").matches && sidebarOpen) {
    sidebarOpen = false;
    sidebar.classList.remove("-translate-x-full");
    backdrop?.classList.add("hidden");
    sidebarTrigger?.setAttribute("aria-expanded", "false");
    document.body.classList.remove("overflow-hidden");
  }
});

document.querySelectorAll("[data-accent-choice]").forEach((button) => {
  button.addEventListener("click", () => {
    preferences.accent = button.dataset.accentChoice;
    savePreferences();
    applyPreferences();
  });
});

document.querySelectorAll("[data-preference-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.preferenceToggle;
    preferences[key] = !preferences[key];
    savePreferences();
    applyPreferences();
  });
});

const showToast = (message, isError = false) => {
  document.querySelector("[data-toast]")?.remove();
  const toast = document.createElement("div");
  toast.dataset.toast = "true";
  toast.className = `fixed bottom-5 right-5 z-50 rounded-xl px-4 py-3 text-sm font-bold text-white shadow-soft ${isError ? "bg-red-600" : "bg-ink"}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  window.setTimeout(() => toast.remove(), 3200);
};

const csrfToken = (form) => form?.querySelector("input[name='csrfmiddlewaretoken']")?.value
  || document.querySelector("input[name='csrfmiddlewaretoken']")?.value
  || "";

const formPayload = (form) => {
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());
  if (form.querySelector("[name='tags']")) {
    payload.tags = formData.getAll("tags");
  }
  if (payload.category === "") payload.category = null;
  if (payload.subcategory === "") payload.subcategory = null;
  return payload;
};

document.querySelectorAll("select").forEach((select) => {
  if (select.closest("form[aria-label='Filter transaction activity']")) return;
  const options = [...select.options];
  if (!options.length) return;

  const group = document.createElement("div");
  group.className = "finance-visual-picker";
  group.setAttribute("role", "radiogroup");
  const label = select.closest("label")?.querySelector("span:not(.sr-only)")?.textContent.trim();
  group.setAttribute("aria-label", label || select.name || "Choose an option");

  const syncOptions = () => {
    group.querySelectorAll("[data-finance-picker-option]").forEach((button) => {
      const selected = button.dataset.value === select.value;
      button.setAttribute("aria-checked", String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
  };

  options.forEach((option) => {
    const button = document.createElement("button");
    const value = option.value;
    const labelText = option.textContent.trim();
    const [primaryText, ...secondaryParts] = labelText.split("·").map((part) => part.trim());
    const secondaryText = secondaryParts.join(" · ");
    const icon = document.createElement("span");
    icon.className = "finance-picker-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = select.name === "account" ? "account_balance_wallet"
      : select.name === "category" ? "category"
        : select.name === "type" || select.name === "direction" ? "swap_vert"
          : select.name === "frequency" || select.name === "period" ? "event_repeat"
            : value ? primaryText.slice(0, 1).toUpperCase() : "tune";
    if (["account", "category", "type", "direction", "frequency", "period"].includes(select.name)) {
      icon.classList.add("material-symbols-outlined");
    }
    const text = document.createElement("span");
    text.className = "finance-picker-copy";
    const title = document.createElement("span");
    title.className = "finance-picker-title";
    title.textContent = primaryText || labelText;
    text.appendChild(title);
    if (secondaryText) {
      const subtitle = document.createElement("span");
      subtitle.className = "finance-picker-subtitle";
      subtitle.textContent = secondaryText;
      text.appendChild(subtitle);
    }
    button.type = "button";
    button.className = "finance-picker-option";
    button.dataset.financePickerOption = "true";
    button.dataset.value = value;
    button.setAttribute("role", "radio");
    button.append(icon, text);
    button.addEventListener("click", () => {
      select.value = value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      select.dispatchEvent(new Event("input", { bubbles: true }));
      syncOptions();
    });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      const choices = [...group.querySelectorAll("[data-finance-picker-option]")];
      const next = choices[(choices.indexOf(button) + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : choices.length - 1)) % choices.length];
      event.preventDefault();
      next?.focus();
      next?.click();
    });
    group.appendChild(button);
  });

  select.classList.add("finance-picker-source");
  select.setAttribute("aria-hidden", "true");
  select.tabIndex = -1;
  if (select.required) {
    select.dataset.financePickerRequired = "true";
    select.required = false;
  }
  select.insertAdjacentElement("afterend", group);
  select.addEventListener("change", syncOptions);
  select.addEventListener("input", syncOptions);
  syncOptions();
});

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const requiredPicker = form.querySelector("select[data-finance-picker-required]");
    if (requiredPicker && !requiredPicker.value) {
      event.preventDefault();
      const group = requiredPicker.nextElementSibling;
      group?.classList.add("finance-picker-invalid");
      group?.querySelector("[data-finance-picker-option]")?.focus();
      showToast("Choose an option before continuing.", true);
    }
  });
});

document.querySelectorAll("[data-confirm-delete]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirmMessage || "Delete this item?")) {
      event.preventDefault();
    }
  });
});

document.querySelectorAll("[data-entry-type-select]").forEach((typeInput) => {
  const form = typeInput.closest("form");
  const choices = [...(form?.querySelectorAll("[data-entry-type-choice]") || [])];
  if (!choices.length) return;

  const syncChoices = () => {
    choices.forEach((button) => {
      const selected = button.dataset.entryTypeChoice === typeInput.value;
      button.setAttribute("aria-checked", String(selected));
    });
  };

  choices.forEach((button, index) => {
    button.addEventListener("click", () => {
      typeInput.value = button.dataset.entryTypeChoice;
      typeInput.dispatchEvent(new Event("change", { bubbles: true }));
      syncChoices();
    });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const nextIndex = (index + (event.key === "ArrowRight" ? 1 : choices.length - 1)) % choices.length;
      choices[nextIndex].focus();
      choices[nextIndex].click();
    });
  });
  typeInput.addEventListener("change", syncChoices);
  syncChoices();
});

document.querySelectorAll("[data-scroll-to]").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById(button.dataset.scrollTo)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

const transactionModal = document.querySelector("#new-transaction");
const setTransactionModal = (open) => {
  if (!transactionModal) return;
  transactionModal.classList.toggle("hidden", !open);
  transactionModal.setAttribute("aria-hidden", String(!open));
  document.body.classList.toggle("overflow-hidden", open);
  if (open) transactionModal.querySelector("input[name='title']")?.focus();
};

document.querySelectorAll("[data-open-transaction-modal]").forEach((button) => {
  button.addEventListener("click", () => setTransactionModal(true));
});
document.querySelectorAll("[data-close-transaction-modal]").forEach((button) => {
  button.addEventListener("click", () => setTransactionModal(false));
});
transactionModal?.addEventListener("click", (event) => {
  if (event.target === transactionModal) setTransactionModal(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (sidebarOpen) toggleSidebar(false);
    setTransactionModal(false);
    setEditModal(false);
    setAccountEditor(false);
    return;
  }

  if (event.key === "Tab" && sidebarOpen) {
    const focusable = [...sidebar.querySelectorAll("a[href], button:not([disabled])")];
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }
});
if (window.location.hash === "#new-transaction") setTransactionModal(true);

const editModal = document.querySelector("#edit-transaction");
const editForm = editModal?.querySelector("[data-transaction-edit-form]");
const setEditModal = (open) => {
  if (!editModal) return;
  editModal.classList.toggle("hidden", !open);
  editModal.setAttribute("aria-hidden", String(!open));
  document.body.classList.toggle("overflow-hidden", open || !transactionModal?.classList.contains("hidden"));
};

document.querySelectorAll("[data-edit-transaction]").forEach((button) => {
  button.addEventListener("click", () => {
    const row = button.closest("[data-transaction-row]");
    if (!row || !editForm) return;
    editForm.action = `/api/finance/transactions/${row.dataset.transactionId}/`;
    editForm.querySelector("[name='title']").value = row.dataset.title;
    editForm.querySelector("[name='amount']").value = row.dataset.amount;
    editForm.querySelector("[name='transaction_date']").value = row.dataset.date;
    editForm.querySelector("[name='account']").value = row.dataset.account;
    editForm.querySelector("[name='account']").dispatchEvent(new Event("change", { bubbles: true }));
    editForm.querySelector("[name='type']").value = row.dataset.type;
    editForm.querySelector("[name='type']").dispatchEvent(new Event("change", { bubbles: true }));
    editForm.querySelector("[name='category']").value = row.dataset.category;
    editForm.querySelector("[name='subcategory']").value = row.dataset.subcategory;
    editForm.querySelector("[name='description']").value = row.dataset.description;
    const selectedTags = new Set(
      (row.dataset.tags || "").split(",").filter(Boolean)
    );
    editForm.querySelectorAll("[name='tags']").forEach((input) => {
      if (input.type === "checkbox") {
        input.checked = selectedTags.has(input.value);
      } else {
        input.selected = selectedTags.has(input.value);
      }
    });
    editForm.querySelector("[name='category']").dispatchEvent(new Event("change"));
    editForm.querySelector("[name='subcategory']").value = row.dataset.subcategory;
    editForm.querySelector("[name='subcategory']").dispatchEvent(new Event("change"));
    editModal.querySelector("#edit-transaction-title").textContent = row.dataset.title || "Transaction";
    setEditModal(true);
  });
});
document.querySelectorAll("[data-close-edit-transaction]").forEach((button) => {
  button.addEventListener("click", () => setEditModal(false));
});
editModal?.addEventListener("click", (event) => {
  if (event.target === editModal) setEditModal(false);
});

const accountModal = document.querySelector("#edit-account-modal");
const accountForm = accountModal?.querySelector("form");
let accountEditTrigger = null;
accountForm?.addEventListener("change", (event) => {
  const input = event.target;
  if (input instanceof HTMLInputElement && input.name === "icon") {
    accountModal.querySelector("[data-account-icon-preview]").textContent = input.value;
  }
});
const setAccountEditor = (open) => {
  if (!accountModal) return;
  accountModal.classList.toggle("hidden", !open);
  accountModal.setAttribute("aria-hidden", String(!open));
  document.body.classList.toggle(
    "overflow-hidden",
    open
      || Boolean(transactionModal && !transactionModal.classList.contains("hidden"))
      || Boolean(editModal && !editModal.classList.contains("hidden"))
  );
  if (open) accountForm?.querySelector("[name='name']")?.focus();
  else accountEditTrigger?.focus();
};

document.querySelectorAll("[data-edit-account]").forEach((button) => {
  button.addEventListener("click", () => {
    if (!accountForm) return;
    accountEditTrigger = button;
    accountForm.querySelector("[data-edit-account-id]").value = button.dataset.accountId;
    accountForm.querySelector("[name='name']").value = button.dataset.accountName;
    const currency = accountForm.querySelector("[data-edit-account-currency]");
    currency.value = button.dataset.accountCurrency;
    currency.readOnly = button.dataset.currencyEditable !== "true";
    accountForm.querySelector("[data-currency-help]").textContent = currency.readOnly
      ? "Currency is locked because this account has a balance or financial activity. Existing amounts are never converted."
      : "Changing currency does not convert any existing balance or transactions.";
    accountModal.querySelector("[data-account-icon-preview]").textContent = button.dataset.accountIcon;
    accountForm.querySelectorAll("[name='icon']").forEach((input) => {
      input.checked = input.value === button.dataset.accountIcon;
    });
    accountForm.querySelectorAll("[name='color']").forEach((input) => {
      input.checked = input.value === button.dataset.accountColor;
    });
    setAccountEditor(true);
  });
});
document.querySelectorAll("[data-close-account-modal]").forEach((button) => {
  button.addEventListener("click", () => setAccountEditor(false));
});
accountModal?.addEventListener("click", (event) => {
  if (event.target === accountModal) setAccountEditor(false);
});

const refreshTransactionFilters = () => {
  const search = document.querySelector("[data-transaction-search]")?.value.toLowerCase().trim() || "";
  const type = document.querySelector("[data-transaction-type]")?.value || "";
  const account = document.querySelector("[data-transaction-account]")?.value || "";
  const rows = [...document.querySelectorAll("[data-transaction-row]")];
  let visibleRows = 0;

  rows.forEach((row) => {
    const matches = (!search || row.dataset.search.toLowerCase().includes(search))
      && (!type || row.dataset.type === type)
      && (!account || row.dataset.account === account);
    row.classList.toggle("hidden", !matches);
    if (matches) visibleRows += 1;
  });

  document.querySelectorAll("[data-transaction-group]").forEach((group) => {
    const hasVisibleRows = [...group.querySelectorAll("[data-transaction-row]")]
      .some((row) => !row.classList.contains("hidden"));
    group.classList.toggle("hidden", !hasVisibleRows);
  });
  document.querySelector("[data-no-results]")?.classList.toggle("hidden", visibleRows !== 0 || rows.length === 0);
  document.querySelector("[data-empty-activity]")?.classList.toggle("hidden", rows.length !== 0);
};

["[data-transaction-search]", "[data-transaction-type]", "[data-transaction-account]"].forEach((selector) => {
  document.querySelector(selector)?.addEventListener("input", refreshTransactionFilters);
  document.querySelector(selector)?.addEventListener("change", refreshTransactionFilters);
});

document.querySelectorAll("[data-subcategory-select]").forEach((subcategorySelect) => {
  const form = subcategorySelect.closest("form");
  const categorySelect = form?.querySelector("[data-category-select]");
  if (!categorySelect) return;
  const categoryOptions = [...form.querySelectorAll("[data-category-option]")];
  const subcategoryOptions = [...form.querySelectorAll("[data-subcategory-option]")];
  const subcategoryField = form.querySelector("[data-subcategory-field]");

  const syncCategoryOptions = () => {
    categoryOptions.forEach((button) => {
      button.setAttribute("aria-pressed", String(
        button.dataset.categoryId === categorySelect.value
      ));
    });
  };

  const filterSubcategories = () => {
    const categoryId = categorySelect.value;
    subcategoryOptions.forEach((button) => {
      const belongsToCategory = Boolean(categoryId)
        && (!button.dataset.categoryId || button.dataset.categoryId === categoryId);
      button.classList.toggle("hidden", !belongsToCategory);
    });
    subcategoryField?.classList.toggle("hidden", !categoryId);
    const selectedOption = subcategoryOptions.find(
      (button) => button.dataset.subcategoryId === subcategorySelect.value
        && !button.classList.contains("hidden")
    );
    if (subcategorySelect.value && !selectedOption) subcategorySelect.value = "";
    subcategoryOptions.forEach((button) => {
      const selected = button.dataset.subcategoryId === subcategorySelect.value;
      button.setAttribute("aria-checked", String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    syncCategoryOptions();
  };

  categorySelect.addEventListener("change", filterSubcategories);
  subcategorySelect.addEventListener("change", filterSubcategories);
  categoryOptions.forEach((button) => {
    button.addEventListener("click", () => {
      categorySelect.value = button.dataset.categoryId;
      categorySelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
  subcategoryOptions.forEach((button) => {
    button.addEventListener("click", () => {
      if (button.classList.contains("hidden")) return;
      subcategorySelect.value = button.dataset.subcategoryId;
      filterSubcategories();
    });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      const visibleOptions = subcategoryOptions.filter(
        (option) => !option.classList.contains("hidden")
      );
      const currentIndex = visibleOptions.indexOf(button);
      const step = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1;
      const nextIndex = (currentIndex + step + visibleOptions.length) % visibleOptions.length;
      event.preventDefault();
      visibleOptions[nextIndex]?.focus();
      visibleOptions[nextIndex]?.click();
    });
  });
  filterSubcategories();
});

document.querySelectorAll("[data-ajax-transaction]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = form.querySelector("button[type='submit']");
    if (submitButton) submitButton.disabled = true;

    try {
      const response = await fetch(form.action, {
        method: form.hasAttribute("data-transaction-row") || form.hasAttribute("data-transaction-edit-form") ? "PATCH" : "POST",
        body: JSON.stringify(formPayload(form)),
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(form),
          "X-Requested-With": "XMLHttpRequest"
        }
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.error || "Unable to save the transaction.");
      showToast("Transaction saved.");
      window.setTimeout(() => {
        if (form.dataset.redirectOnSave) {
          window.location.assign(form.dataset.redirectOnSave);
        } else {
          window.location.reload();
        }
      }, 350);
    } catch (error) {
      showToast(error.message, true);
      if (submitButton) submitButton.disabled = false;
    }
  });
});

document.querySelectorAll("[data-delete-transaction]").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!window.confirm("Delete this transaction?")) return;
    const form = button.closest("[data-transaction-row]");
    try {
      const response = await fetch(button.dataset.deleteUrl, {
        method: "DELETE",
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": csrfToken(form),
          "X-Requested-With": "XMLHttpRequest"
        }
      });
      const data = response.status === 204 ? {} : await response.json();
      if (!response.ok) throw new Error(data.detail || data.error || "Unable to delete the transaction.");
      form.remove();
      refreshTransactionFilters();
      showToast("Transaction deleted.");
    } catch (error) {
      showToast(error.message, true);
    }
  });
});

applyPreferences();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker
    .register("/service-worker.js")
    .catch((error) => console.error("Service worker registration failed:", error));
}
const sidebar = document.querySelector("#sidebar");
const backdrop = document.querySelector("#sidebar-backdrop");
const preferenceKey = "ledger-preferences";

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
  sidebar?.classList.toggle("-translate-x-full", !open);
  backdrop?.classList.toggle("hidden", !open);
};

document.querySelector("[data-sidebar-open]")?.addEventListener("click", () => toggleSidebar(true));
document.querySelector("[data-sidebar-close]")?.addEventListener("click", () => toggleSidebar(false));
backdrop?.addEventListener("click", () => toggleSidebar(false));

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
  const payload = Object.fromEntries(new FormData(form).entries());
  if (payload.category === "") payload.category = null;
  if (payload.subcategory === "") payload.subcategory = null;
  return payload;
};

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
    setTransactionModal(false);
    setEditModal(false);
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
    editForm.querySelector("[name='type']").value = row.dataset.type;
    editForm.querySelector("[name='category']").value = row.dataset.category;
    editForm.querySelector("[name='subcategory']").value = row.dataset.subcategory;
    editForm.querySelector("[name='description']").value = row.dataset.description;
    editForm.querySelector("[name='category']").dispatchEvent(new Event("change"));
    editForm.querySelector("[name='subcategory']").value = row.dataset.subcategory;
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
  document.querySelector("[data-no-results]")?.classList.toggle("hidden", visibleRows !== 0 || rows.length === 0);
};

["[data-transaction-search]", "[data-transaction-type]", "[data-transaction-account]"].forEach((selector) => {
  document.querySelector(selector)?.addEventListener("input", refreshTransactionFilters);
  document.querySelector(selector)?.addEventListener("change", refreshTransactionFilters);
});

document.querySelectorAll("[data-subcategory-select]").forEach((subcategorySelect) => {
  const form = subcategorySelect.closest("form");
  const categorySelect = form?.querySelector("[data-category-select]");
  if (!categorySelect) return;

  const filterSubcategories = () => {
    const categoryId = categorySelect.value;
    [...subcategorySelect.options].forEach((option) => {
      const belongsToCategory = !option.value || !categoryId || option.dataset.category === categoryId;
      option.hidden = !belongsToCategory;
    });
    const selectedOption = subcategorySelect.selectedOptions[0];
    if (selectedOption?.hidden) subcategorySelect.value = "";
  };

  categorySelect.addEventListener("change", filterSubcategories);
  subcategorySelect.addEventListener("change", () => {
    const selectedOption = subcategorySelect.selectedOptions[0];
    if (selectedOption?.dataset.category) {
      categorySelect.value = selectedOption.dataset.category;
      filterSubcategories();
      subcategorySelect.value = selectedOption.value;
    }
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
      window.setTimeout(() => window.location.reload(), 350);
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
  navigator.serviceWorker.register("/static/service-worker.js").catch(() => {});
}
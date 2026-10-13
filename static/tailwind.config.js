window.tailwind = window.tailwind || {};
window.tailwind.config = {
  theme: {
    extend: {
      fontFamily: {
        sans: ["DM Sans", "ui-sans-serif", "system-ui"],
        display: ["Nunito", "ui-sans-serif", "system-ui"]
      },
      colors: {
        ink: "#49394f",
        mist: "#fbf7f4",
        mint: "#e8f3e8",
        coral: "#f3a18d"
      },
      boxShadow: {
        soft: "0 14px 34px -26px rgba(73, 57, 79, .30)"
      }
    }
  }
};
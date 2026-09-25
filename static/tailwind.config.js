window.tailwind = window.tailwind || {};
window.tailwind.config = {
  theme: {
    extend: {
      fontFamily: {
        sans: ["DM Sans", "ui-sans-serif", "system-ui"],
        display: ["Space Grotesk", "ui-sans-serif", "system-ui"]
      },
      colors: {
        ink: "#183b56",
        mist: "#edf4f7",
        mint: "#d9eee5",
        coral: "#2f8f9d"
      },
      boxShadow: {
        soft: "0 18px 50px -28px rgba(16, 42, 67, .35)"
      }
    }
  }
};
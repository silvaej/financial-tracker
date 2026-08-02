function togglePasswordVisibility(buttonEl) {
  const input = buttonEl.parentElement.querySelector("input");
  const showing = input.type === "text";
  input.type = showing ? "password" : "text";
  buttonEl.querySelector(".pw-icon-show").classList.toggle("hidden", !showing);
  buttonEl.querySelector(".pw-icon-hide").classList.toggle("hidden", showing);
}

// Auto-dismiss flash alerts after 4s
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    document.querySelectorAll('.alert.fade.show').forEach(el => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      bsAlert.close();
    });
  }, 4000);

  // Format currency inputs on blur
  document.querySelectorAll('input[name="amount"], input[name="amount_paid"]').forEach(inp => {
    inp.addEventListener('blur', () => {
      const val = parseFloat(inp.value.replace(',', '.'));
      if (!isNaN(val)) inp.value = val.toFixed(2).replace('.', ',');
    });

    // Allow only numbers and comma/dot
    inp.addEventListener('keypress', e => {
      if (!/[\d,.]/.test(e.key) && !['Backspace','Delete','Tab','ArrowLeft','ArrowRight'].includes(e.key)) {
        e.preventDefault();
      }
    });
  });
});

// ── Formato pt-BR (espelha format_brl/parse_brl do back-end) ─────────────────
// Definidos aqui porque base.html carrega este arquivo antes dos scripts de pagina.
function brl(v) {
  return (Number(v) || 0).toLocaleString('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// Le o que o usuario digitou: '4.500,00', '4500,00' ou '4500'
function brlParse(texto) {
  let limpo = String(texto == null ? '' : texto).trim().replace(/R\$/g, '').replace(/\s/g, '');
  if (!limpo) return NaN;
  // virgula e o decimal: os pontos sao separadores de milhar
  if (limpo.includes(',')) limpo = limpo.replace(/\./g, '').replace(',', '.');
  const n = parseFloat(limpo);
  return Number.isFinite(n) ? n : NaN;
}

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
      const val = brlParse(inp.value);
      if (!isNaN(val)) inp.value = brl(val);
    });

    // Allow only numbers and comma/dot
    inp.addEventListener('keypress', e => {
      if (!/[\d,.]/.test(e.key) && !['Backspace','Delete','Tab','ArrowLeft','ArrowRight'].includes(e.key)) {
        e.preventDefault();
      }
    });
  });
});

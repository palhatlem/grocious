'use strict';
const editor = document.querySelector('[data-line-editor]');
if (editor) {
  const fields = ['name', 'qty', 'unit', 'amount', 'discount', 'kind'];
  const body = editor.querySelector('tbody');
  function add(line = {}) {
    const row = document.createElement('tr');
    fields.forEach(key => {
      const td = document.createElement('td');
      const input = document.createElement('input');
      input.dataset.field = key; input.value = line[key] ?? '';
      input.setAttribute('aria-label', {name:'Vare',qty:'Antall',unit:'Enhet',amount:'Beløp',discount:'Rabatt',kind:'Type'}[key]);
      if (['qty','amount','discount'].includes(key)) input.inputMode = 'decimal';
      td.append(input); row.append(td);
    });
    const td = document.createElement('td'), remove = document.createElement('button');
    remove.type = 'button'; remove.textContent = 'Fjern'; remove.onclick = () => row.remove();
    td.append(remove); row.append(td); body.append(row);
  }
  JSON.parse(document.getElementById('inbox-lines').textContent).forEach(add);
  document.getElementById('add-line').onclick = () => add({kind:'item'});
  editor.closest('form').addEventListener('submit', () => {
    const lines = [...body.rows].map(row => Object.fromEntries([...row.querySelectorAll('input')].map(input => [input.dataset.field, input.value || null])));
    document.getElementById('lines-value').value = JSON.stringify(lines);
  });
}

// Mouse: prévia ao passar pelo cartão. Toque/teclado: summary nativo.
// Não altera status nem envia requisições ao servidor.
document.querySelectorAll('.kanban-ticket').forEach((card) => {
    const details = card.querySelector('details');
    let openedByHover = false;
    card.addEventListener('pointerenter', (event) => {
        if (event.pointerType !== 'mouse' || details.open) return;
        openedByHover = true;
        details.open = true;
    });
    card.addEventListener('pointerleave', () => {
        if (openedByHover && !card.contains(document.activeElement)) details.open = false;
        openedByHover = false;
    });
    card.querySelector('a').addEventListener('focus', () => { details.open = true; });
    card.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            details.open = false;
            openedByHover = false;
        }
    });
});

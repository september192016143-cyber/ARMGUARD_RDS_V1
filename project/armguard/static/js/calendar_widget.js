/**
 * calendar_widget.js — Date-range calendar dropdown.
 *
 * Used by transaction_list.html and print/print_transactions.html.
 * Expects the following IDs in the HTML:
 *   #cal-wrap, #calendar-toggle, #calendar-dropdown, #cal-range-bar,
 *   #cal-range-txt, #cal-month-label, #cal-grid, #cal-prev, #cal-next,
 *   #cal-apply, #cal-clear
 */
(function () {
  'use strict';

  const MONTHS = ['January','February','March','April','May','June',
                  'July','August','September','October','November','December'];
  let viewYear, viewMonth, selStart = null, selEnd = null, picking = 0;

  function toYMD(d) {
    return d.getFullYear() + '-' +
           String(d.getMonth() + 1).padStart(2, '0') + '-' +
           String(d.getDate()).padStart(2, '0');
  }
  function fromYMD(s) { const p = s.split('-'); return new Date(+p[0], +p[1]-1, +p[2]); }
  function sameDay(a, b) { return a && b && toYMD(a) === toYMD(b); }

  function renderCal() {
    document.getElementById('cal-month-label').textContent =
      MONTHS[viewMonth] + ' ' + viewYear;
    const grid = document.getElementById('cal-grid');
    grid.innerHTML = '';
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const firstDay = new Date(viewYear, viewMonth, 1).getDay();
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const daysInPrev  = new Date(viewYear, viewMonth, 0).getDate();

    for (let i = 0; i < firstDay; i++) {
      const d = document.createElement('div');
      d.className = 'cal-day cal-empty cal-other-month';
      d.textContent = daysInPrev - firstDay + 1 + i;
      grid.appendChild(d);
    }
    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(viewYear, viewMonth, day);
      const d = document.createElement('div');
      d.className = 'cal-day';
      d.textContent = day;
      if (sameDay(date, today))  d.classList.add('cal-today');
      if (selStart && sameDay(date, selStart)) d.classList.add('cal-start');
      if (selEnd   && sameDay(date, selEnd))   d.classList.add('cal-end');
      if (selStart && selEnd) {
        const t = date.getTime();
        if (t > selStart.getTime() && t < selEnd.getTime()) d.classList.add('cal-in-range');
      }
      d.addEventListener('click', function (e) { e.stopPropagation(); dayClick(date); });
      grid.appendChild(d);
    }
    const remaining = (7 - (firstDay + daysInMonth) % 7) % 7;
    for (let i = 1; i <= remaining; i++) {
      const d = document.createElement('div');
      d.className = 'cal-day cal-empty cal-other-month';
      d.textContent = i;
      grid.appendChild(d);
    }
  }

  function dayClick(date) {
    if (picking === 0 || picking === 2) {
      selStart = date; selEnd = null; picking = 1;
      document.getElementById('cal-range-txt').textContent =
        toYMD(selStart) + ' \u2192 pick end date';
    } else {
      if (date < selStart) { selEnd = selStart; selStart = date; }
      else selEnd = date;
      picking = 2;
      document.getElementById('cal-range-txt').textContent =
        toYMD(selStart) + ' \u2192 ' + toYMD(selEnd);
    }
    renderCal();
  }

  function calNav(dir) {
    viewMonth += dir;
    if (viewMonth > 11) { viewMonth = 0; viewYear++; }
    if (viewMonth < 0)  { viewMonth = 11; viewYear--; }
    renderCal();
  }

  function applyCalendar() {
    if (!selStart) return;
    const from = toYMD(selStart);
    const to   = selEnd ? toYMD(selEnd) : from;
    const url  = new URL(window.location.href);
    url.searchParams.set('date_from', from);
    url.searchParams.set('date_to',   to);
    document.getElementById('calendar-toggle').style.boxShadow = '0 0 16px rgba(245,158,11,.6)';
    document.getElementById('calendar-dropdown').style.display = 'none';
    window.location.href = url.toString();
  }

  function clearCalendar() {
    selStart = null; selEnd = null; picking = 0;
    document.getElementById('cal-range-txt').textContent = 'Select start date';
    document.getElementById('calendar-toggle').style.boxShadow = '0 0 8px rgba(245,158,11,.2)';
    const url = new URL(window.location.href);
    url.searchParams.delete('date_from');
    url.searchParams.delete('date_to');
    document.getElementById('calendar-dropdown').style.display = 'none';
    window.location.href = url.toString();
  }

  // ── Wire nav / action buttons ── ─────────────────────────────────────────────
  document.getElementById('cal-prev').addEventListener('click', () => calNav(-1));
  document.getElementById('cal-next').addEventListener('click', () => calNav(1));
  document.getElementById('cal-apply').addEventListener('click', (e) => {
    e.stopPropagation(); applyCalendar();
  });
  document.getElementById('cal-clear').addEventListener('click', (e) => {
    e.stopPropagation(); clearCalendar();
  });

  // ── Toggle dropdown ──────────────────────────────────────────────────────────
  document.getElementById('calendar-toggle').addEventListener('click', (e) => {
    e.stopPropagation();
    const d = document.getElementById('calendar-dropdown');
    d.style.display = d.style.display === 'none' ? 'block' : 'none';
  });
  document.getElementById('calendar-dropdown').addEventListener('click', (e) => e.stopPropagation());
  document.addEventListener('click', () => {
    const d = document.getElementById('calendar-dropdown');
    if (d) d.style.display = 'none';
  });

  // ── Init from URL params ─────────────────────────────────────────────────────
  const p = new URLSearchParams(window.location.search);
  const today = new Date();
  if (p.get('date_from')) { selStart = fromYMD(p.get('date_from')); picking = 1; }
  if (p.get('date_to'))   { selEnd   = fromYMD(p.get('date_to'));   picking = 2; }
  if (selStart && selEnd)
    document.getElementById('cal-range-txt').textContent = toYMD(selStart) + ' \u2192 ' + toYMD(selEnd);
  else if (selStart)
    document.getElementById('cal-range-txt').textContent = toYMD(selStart) + ' \u2192 pick end date';
  if (selStart) {
    viewYear  = selStart.getFullYear();
    viewMonth = selStart.getMonth();
    document.getElementById('calendar-toggle').style.boxShadow = '0 0 16px rgba(245,158,11,.6)';
  } else {
    viewYear  = today.getFullYear();
    viewMonth = today.getMonth();
  }
  renderCal();
}());


    if(typeof claude === 'undefined'){
      local = true; votes = lsGet();
      try{ myId = localStorage.getItem('wybor-elesa-imie') || ''; }catch(e){}
      var w = $('who'); w.hidden = false; w.value = myId || '';
      w.addEventListener('input', function(){ myId = w.value.trim(); try{ localStorage.setItem('wybor-elesa-imie', myId); }catch(e){} });
      showNotice('Wybór zapisuje się w tej przeglądarce. Po zakończeniu wpisz imię, kliknij „Zapisz mój wybór (CSV)” i zostaw plik w folderze „wybory” obok tej strony.');
      $('csv').hidden = false;
      $('csv').addEventListener('click', function(){
        var gname = {}; GROUPS.forEach(function(g){gname[g.k]=g.t});
        var rows = [['Osoba','Grupa','Oznaczenie','Kod','Opis','Do biblioteki','Status decyzji']];
        ITEMS.forEach(function(it){ rows.push([myId||'', gname[it.g], it.n, it.kod, it.opis, isOn(it)?'TAK':'NIE', decided(it)?'decyzja':'propozycja']); });
        var txt = '﻿' + rows.map(function(r){ return r.map(function(c){ return '"'+String(c==null?'':c).replace(/"/g,'""')+'"'; }).join(';'); }).join('\r\n');
        var blob = new Blob([txt], {type:'text/csv;charset=utf-8'});
        var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = 'wybor_elesa_' + (myId ? myId.replace(/[^\w\-]+/g,'_') : 'osoba') + '.csv';
        document.body.appendChild(a); a.click(); a.remove();
      });
      renderAll(); return;
    }

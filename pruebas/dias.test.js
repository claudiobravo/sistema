// Selector de día e historial, en un navegador de verdad.
//   npm i playwright-core   &&   node pruebas/dias.test.js
var U=require('./util.js');
var chk=U.chk, seccion=U.seccion;

(async function(){
  var s=await U.abrir(), pg=s.pg;

  seccion('Se abre en hoy');
  chk('no deja ir al futuro', await pg.isDisabled('#diaNext'));
  chk('la etiqueta dice hoy', (await pg.textContent('#diaEtiq'))==='hoy');
  await pg.fill('#estudio','45'); await pg.fill('#clips','10'); await pg.fill('#cuerpo','20');
  await pg.click('.tg[data-tg="liquidacion"]'); await pg.waitForTimeout(200);
  chk('calcula la EXP del día', Number(await pg.textContent('#expNum'))>0);

  seccion('Retroceder tres días');
  for(var i=0;i<3;i++){ await pg.click('#diaPrev'); await pg.waitForTimeout(120); }
  chk('los campos se vacían y no se arrastran',
      (await pg.inputValue('#estudio'))==='' && (await pg.inputValue('#clips'))==='',
      {estudio:await pg.inputValue('#estudio')});
  chk('el interruptor se apaga', !(await pg.getAttribute('.tg[data-tg="liquidacion"]','class')).includes('on'));
  chk('avisa de que el día está sin registrar', (await pg.textContent('#aviso')).includes('Día sin registrar'));
  chk('ahora sí se puede avanzar', !(await pg.isDisabled('#diaNext')));
  chk('ofrece volver a hoy', (await pg.textContent('#diaEtiq')).includes('volver a hoy'));

  seccion('Rellenar un día pasado');
  await pg.fill('#estudio','30'); await pg.fill('#cuerpo','15'); await pg.fill('#clips','10');
  await pg.click('.tg[data-tg="liquidacion"]'); await pg.waitForTimeout(250);
  chk('la misión de ese día se completa', (await pg.$$eval('#quests .q.done',function(n){return n.length;}))===5);

  var dias=await pg.evaluate(function(){return JSON.parse(localStorage.getItem('sistema.v1')).dias;});
  var claves=Object.keys(dias).sort();
  chk('se guardan los dos días, y solo esos', claves.length===2, claves);
  chk('el de hoy guarda sus 45 min', dias[U.hoy()] && dias[U.hoy()].estudio==='45', dias[U.hoy()]);
  chk('el pasado guarda sus 30 min', dias[U.hace(3)] && dias[U.hace(3)].estudio==='30', dias[U.hace(3)]);
  chk('cada uno con su hora', claves.every(function(k){return dias[k].ts>0;}));
  chk('los días de paso no dejan rastro',
      !claves.includes(U.hace(1)) && !claves.includes(U.hace(2)), claves);

  seccion('Historial');
  await pg.click('nav button[data-v="estado"]'); await pg.waitForTimeout(300);
  chk('se pinta', (await pg.$$eval('#historial .row',function(n){return n.length;}))>0);
  chk('marca los dos días completos', (await pg.$$eval('#historial .rk.ok',function(n){return n.length;}))===2);
  chk('y enseña los huecos', (await pg.$$eval('#historial .row.hueco',function(n){return n.length;}))>0);
  chk('el Estado cuenta 2 días', (await pg.textContent('#sDias'))==='2');

  seccion('Saltar a un día desde el historial');
  var hueco=await pg.$$eval('#historial .row.hueco',function(n){return n[0].dataset.dia;});
  await pg.click('#historial .row[data-dia="'+hueco+'"]'); await pg.waitForTimeout(300);
  chk('lleva a la vista Hoy', await pg.isVisible('#v-hoy.view.on'));
  chk('con ese día abierto y vacío', (await pg.inputValue('#estudio'))==='');
  await pg.click('#diaVolver'); await pg.waitForTimeout(250);
  chk('el botón devuelve a hoy', (await pg.textContent('#diaEtiq'))==='hoy');
  chk('con sus datos intactos', (await pg.inputValue('#estudio'))==='45');

  seccion('Recarga');
  await pg.reload(); await pg.waitForTimeout(600);
  chk('no se pierde nada', (await pg.inputValue('#estudio'))==='45');

  await s.nav.close();
  U.comprobarConsola(s.errores);
  U.resumen();
})();

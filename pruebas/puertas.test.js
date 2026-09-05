// Puertas: las caducadas no desaparecen y las Rojas avisan en Hoy.
// Lo que se espera se deduce de las Puertas declaradas en index.html y de la
// fecha de hoy, para que la prueba no caduque con ellas.
//   npm i playwright-core   &&   node pruebas/puertas.test.js
var fs=require('fs'), path=require('path');
var U=require('./util.js');
var chk=U.chk, seccion=U.seccion;

function puertasDeclaradas(){
  var html=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
  var bloque=html.match(/var PUERTAS=\[([\s\S]*?)\n\];/);
  if(!bloque) throw new Error('no encuentro el array PUERTAS en index.html');
  var re=/\{n:'((?:[^'\\]|\\.)*)',f:'(\d{4}-\d{2}-\d{2})',r:'([A-Z])',roja:(true|false)\}/g, m, out=[];
  while((m=re.exec(bloque[1]))) out.push({n:m[1],f:m[2],r:m[3],roja:m[4]==='true'});
  return out;
}
function dias(f){
  return Math.round((new Date(f+'T12:00')-new Date(U.hoy()+'T12:00'))/86400000);
}

(async function(){
  var todas=puertasDeclaradas();
  var abiertas=todas.filter(function(p){return dias(p.f)>=0;});
  var cerradas=todas.filter(function(p){return dias(p.f)<0;});
  var perdidas=cerradas.filter(function(p){return p.roja;});
  var cerca=abiertas.filter(function(p){return p.roja && dias(p.f)<=14;});
  console.log('Puertas declaradas: '+todas.length+'  ·  abiertas hoy: '+abiertas.length+
              '  ·  cerradas: '+cerradas.length+'  ·  Rojas perdidas: '+perdidas.length+
              '  ·  Rojas a ≤14 días: '+cerca.length);

  var s=await U.abrir(), pg=s.pg;

  seccion('Aviso de Puerta Roja en la pantalla de Hoy');
  var aviso=await pg.textContent('#rojas');
  if(cerca.length){
    chk('avisa', aviso.includes('Puerta Roja'), aviso.slice(0,50));
    chk('nombra las que vienen', cerca.every(function(p){return aviso.includes(p.n);}), cerca.map(function(p){return p.n;}));
    chk('una línea por Puerta', (await pg.$$eval('.aviso-roja .pr',function(n){return n.length;}))===cerca.length);
    chk('dice cuánto queda', (await pg.$$eval('.aviso-roja .pr .c',function(n){return n.map(function(x){return x.textContent;});}))
        .every(function(t){return /^(HOY|MAÑANA|\d+ D)$/.test(t);}));
    chk('las lejanas no cuelan', !abiertas.filter(function(p){return dias(p.f)>14;})
        .some(function(p){return aviso.includes(p.n);}));
  }else{
    chk('sin Rojas cerca, no molesta', aviso.trim()==='');
  }

  seccion('Las caducadas no desaparecen');
  await pg.click('nav button[data-v="puertas"]'); await pg.waitForTimeout(300);
  var vAbiertas=await pg.$$eval('#puertas .row[data-p]',function(n){return n.length;});
  var vCerradas=await pg.$$eval('#puertasCerradas .row',function(n){return n.length;});
  chk('no se pierde ninguna por el camino', vAbiertas+vCerradas===todas.length, {vAbiertas:vAbiertas,vCerradas:vCerradas,total:todas.length});
  chk('las abiertas cuadran', vAbiertas===abiertas.length, vAbiertas);
  chk('las cerradas cuadran', vCerradas===cerradas.length, vCerradas);
  chk('la sección de cerradas se ve solo si hay', (await pg.isVisible('#secCerradas'))===(cerradas.length>0));
  chk('las Rojas que se cerraron van marcadas',
      (await pg.$$eval('#puertasCerradas .row.perdida',function(n){return n.length;}))===perdidas.length);
  var avisoP=await pg.textContent('#avisoPuertas');
  chk('y se avisa de ellas', perdidas.length===0 ? avisoP.trim()==='' :
      avisoP.includes(perdidas.length===1?'Una Puerta Roja se cerró':perdidas.length+' Puertas Rojas se cerraron'), avisoP);

  if(perdidas.length){
    seccion('Marcar una como superada');
    await pg.click('#puertasCerradas .row.perdida'); await pg.waitForTimeout(250);
    chk('baja la cuenta de perdidas',
        (await pg.$$eval('#puertasCerradas .row.perdida',function(n){return n.length;}))===perdidas.length-1);
    chk('la fila pasa a superada',
        (await pg.$$eval('#puertasCerradas .row.hecha .cd',function(n){return n[0].textContent;}))==='superada');

    seccion('Desmarcar deja lápida, para que no vuelva de GitHub');
    await pg.click('#puertasCerradas .row.hecha'); await pg.waitForTimeout(250);
    var g=await pg.evaluate(function(){return JSON.parse(localStorage.getItem('sistema.v1')).puertas;});
    chk('la clave sigue, con superada:false',
        Object.keys(g).some(function(k){return g[k].superada===false;}), g);
    chk('vuelve a contar como perdida',
        (await pg.$$eval('#puertasCerradas .row.perdida',function(n){return n.length;}))===perdidas.length);
  }

  if(cerca.length){
    seccion('Superar una Puerta la quita del aviso de Hoy');
    await pg.click('#puertas .row.red'); await pg.waitForTimeout(250);
    await pg.click('nav button[data-v="hoy"]'); await pg.waitForTimeout(250);
    var quedan=await pg.$$eval('.aviso-roja .pr',function(n){return n.length;}).catch(function(){return 0;});
    chk('queda una menos en el aviso', quedan===cerca.length-1, quedan);

    seccion('Persistencia');
    await pg.reload(); await pg.waitForTimeout(600);
    await pg.click('nav button[data-v="puertas"]'); await pg.waitForTimeout(300);
    chk('aguanta la recarga', (await pg.$$eval('#puertas .row.hecha',function(n){return n.length;}))===1);
  }

  await s.nav.close();
  U.comprobarConsola(s.errores);
  U.resumen();
})();

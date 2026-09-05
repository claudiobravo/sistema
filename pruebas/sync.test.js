// Motor de sincronización: fusión, reintentos y cortes de red.
// No necesita navegador ni conexión: la red va simulada.
//   node pruebas/sync.test.js
var U=require('./util.js');
var chk=U.chk, seccion=U.seccion;

var LOG=[], RED=null;
global.fetch=function(url,opts){
  opts=opts||{};
  LOG.push({m:opts.method||'GET',url:url,body:opts.body});
  return RED(url,opts);
};

var T=require('./cargar.js');
var esperar=function(ms){return new Promise(function(r){setTimeout(r,ms);});};
var b64=function(o){return Buffer.from(JSON.stringify(o),'utf8').toString('base64');};

// Simula GitHub: qué hay guardado y qué falla.
function red(o){
  o=o||{};
  return function(url,opts){
    if((opts.method||'GET')==='GET'){
      if(o.getFalla) return Promise.reject(new Error('conexión cortada'));
      if(!o.remoto) return Promise.resolve({ok:false,status:404});
      return Promise.resolve({ok:true,status:200,
        json:function(){return Promise.resolve({sha:'SHA1',content:b64({dias:o.remoto,puertas:o.puertas||{}})});}});
    }
    if(o.putFalla) return Promise.reject(new Error('conexión cortada'));
    var st=o.putStatus||200;
    return Promise.resolve({ok:st<300,status:st,json:function(){return Promise.resolve({content:{sha:'SHA2'}});}});
  };
}

(async function(){
  seccion('Móvil nuevo: GitHub tiene datos y el móvil no');
  T.S.cfg.token='tok'; T.S.dias={}; T.S.pendiente=false; T.SYNC.intento=0; T.SYNC.error='';
  LOG=[]; RED=red({remoto:{'2026-08-20':{tocado:true,estudio:'40',ts:1000}}});
  T.sincronizar(true); await esperar(60);
  chk('baja el día de GitHub', !!T.S.dias['2026-08-20'], Object.keys(T.S.dias));
  chk('no hace un commit inútil', LOG.filter(function(x){return x.m==='PUT';}).length===0);

  seccion('Un día vacío en local no borra el de GitHub');
  T.S.dias={'2026-08-20':{}}; T.S.pendiente=false;
  RED=red({remoto:{'2026-08-20':{tocado:true,estudio:'40',ts:1000}}});
  T.sincronizar(true); await esperar(60);
  chk('gana el registro que tiene datos', T.S.dias['2026-08-20'].estudio==='40', T.S.dias['2026-08-20']);

  seccion('Gana siempre la escritura más reciente');
  T.S.dias={'2026-08-20':{tocado:true,estudio:'99',ts:5000}}; T.S.pendiente=true;
  LOG=[]; RED=red({remoto:{'2026-08-20':{tocado:true,estudio:'40',ts:1000}}});
  T.sincronizar(true); await esperar(60);
  chk('el local nuevo se impone', T.S.dias['2026-08-20'].estudio==='99');
  chk('y se sube', LOG.some(function(x){return x.m==='PUT';}));
  T.S.dias={'2026-08-20':{tocado:true,estudio:'99',ts:500}}; T.S.pendiente=false;
  RED=red({remoto:{'2026-08-20':{tocado:true,estudio:'40',ts:9000}}});
  T.sincronizar(true); await esperar(60);
  chk('el remoto nuevo se impone', T.S.dias['2026-08-20'].estudio==='40');

  seccion('Se cae la red: reintenta solo');
  T.S.dias={'2026-08-21':{tocado:true,estudio:'30',ts:Date.now()}}; T.S.pendiente=true;
  T.SYNC.intento=0; T.SYNC.error=''; clearTimeout(T.SYNC.timer);
  LOG=[]; RED=red({getFalla:true});
  T.sincronizar(false); await esperar(60);
  chk('marca el fallo', !!T.SYNC.error, T.SYNC.error);
  chk('deja el reintento programado', !!T.SYNC.timer);
  chk('sigue pendiente', T.S.pendiente===true);
  RED=red({remoto:null});                     // vuelve la cobertura
  await esperar(4600);                        // la primera espera es de 4 s
  chk('reintenta al volver la cobertura', LOG.some(function(x){return x.m==='PUT';}));
  chk('y queda limpio', T.S.pendiente===false && T.SYNC.error==='');

  seccion('Sin conexión no se pierde nada');
  navigator.onLine=false; T.S.pendiente=true; T.SYNC.intento=0; T.SYNC.error='';
  LOG=[]; RED=red({remoto:null});
  T.sincronizar(false); await esperar(40);
  chk('ni siquiera llama a la red', LOG.length===0, LOG);
  chk('deja el reintento en cola', !!T.SYNC.timer);
  navigator.onLine=true; clearTimeout(T.SYNC.timer);

  seccion('Choque de sha (409): no se da por bueno');
  T.S.pendiente=true; T.SYNC.intento=0; T.SYNC.error='';
  RED=red({remoto:{'2026-08-21':{tocado:true,ts:1}},putStatus:409});
  T.sincronizar(true); await esperar(60);
  chk('sigue pendiente y con error', T.S.pendiente===true && !!T.SYNC.error, T.SYNC.error);
  clearTimeout(T.SYNC.timer);

  seccion('Puertas: la marca de superada también viaja');
  var P='2026-08-27|Matrícula UOC';
  T.S.dias={}; T.S.puertas={}; T.S.puertas[P]={superada:true,ts:5000}; T.S.pendiente=true;
  T.SYNC.intento=0; T.SYNC.error=''; LOG=[];
  RED=red({remoto:{},puertas:{}});
  T.sincronizar(true); await esperar(60);
  var put=LOG.find(function(x){return x.m==='PUT';});
  var enviado=JSON.parse(Buffer.from(JSON.parse(put.body).content,'base64').toString('utf8'));
  chk('la puerta superada sube a GitHub', enviado.puertas[P].superada===true, enviado.puertas);

  T.S.puertas={}; T.S.puertas[P]={superada:true,ts:5000}; T.S.pendiente=false;
  RED=red({remoto:{},puertas:(function(){var o={};o[P]={superada:false,ts:9000};return o;})()});
  T.sincronizar(true); await esperar(60);
  chk('desmarcar en otro sitio gana si es más reciente', T.S.puertas[P].superada===false);

  T.S.puertas={}; T.S.puertas[P]={superada:true,ts:9000}; T.S.pendiente=false;
  RED=red({remoto:{},puertas:(function(){var o={};o[P]={superada:false,ts:5000};return o;})()});
  T.sincronizar(true); await esperar(60);
  chk('una marca vieja no pisa a la reciente', T.S.puertas[P].superada===true);

  T.S.puertas={}; T.S.pendiente=false;
  RED=red({remoto:{},puertas:(function(){var o={};o[P]={superada:true,ts:7000};return o;})()});
  T.sincronizar(true); await esperar(60);
  chk('un móvil nuevo se trae las puertas', T.S.puertas[P] && T.S.puertas[P].superada===true, T.S.puertas);
  clearTimeout(T.SYNC.timer);

  seccion('EXP y Misión Diaria');
  var completo={tocado:true,estudio:'30',cuerpo:'10',liquidacion:true,clips:'10'};
  chk('misión completa', T.misionCompleta(completo)===true);
  chk('incompleta sin los clips', T.misionCompleta(Object.assign({},completo,{clips:'2'}))===false);
  chk('EXP de un día completo', T.exp(completo)===50+12+3+30, T.exp(completo));
  chk('EXP negativa si se falla', T.exp({tocado:true,estudio:'0'})===-30);
  chk('un día sin tocar no cuenta', T.exp({})===0);
  chk('el descanso no penaliza', T.exp({tocado:true,tipo:'Descanso'})===10);

  U.resumen();
})();

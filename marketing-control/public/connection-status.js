export function connectionStatus(instance){
 if(!instance.desired)return {label:'Desactivado',tone:''};
 if(!instance.worker_online)return {label:'Servicio sin respuesta',tone:'bad'};
 return ({
  CONNECTED:{label:'Conectado',tone:'good'},
  QR_READY:{label:'Sin vincular · escanea el QR',tone:'warn'},
  CONNECTING:{label:'Conectando',tone:'warn'},
  STOPPING:{label:'Deteniendo',tone:'warn'},
  DISCONNECTED:{label:'Desconectado',tone:'warn'},
  ERROR:{label:'Requiere atención',tone:'bad'}
 })[instance.status]||{label:'Estado desconocido',tone:'warn'};
}

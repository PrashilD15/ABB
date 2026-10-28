import {useEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
import {Activity,Check,Square} from 'lucide-react';
import './operation.css';

type Step={command:string;pass:boolean};
export default function OperationOverlay({title,functional,steps,canAbort,aborting,onAbort,error}:{title:string;functional:boolean;steps:Step[];canAbort:boolean;aborting:boolean;onAbort:()=>void;error:string}){
 const dialog=useRef<HTMLDivElement>(null);
 useEffect(()=>{
   const previous=document.activeElement as HTMLElement|null;
   const overflow=document.body.style.overflow;
   document.body.style.overflow='hidden';dialog.current?.focus();
   const trap=(event:KeyboardEvent)=>{
     if(event.key==='Escape'){event.preventDefault();event.stopPropagation();}
     if(event.key==='Tab'){
       event.preventDefault();
       const abort=dialog.current?.querySelector<HTMLButtonElement>('button:not(:disabled)');
       if(abort)abort.focus();else dialog.current?.focus();
     }
   };
   document.addEventListener('keydown',trap,true);
   return()=>{document.body.style.overflow=overflow;document.removeEventListener('keydown',trap,true);if(previous?.isConnected)previous.focus();};
 },[]);
 return createPortal(<div className="operation-backdrop"><div className="operation-dialog" role="dialog" aria-modal="true" aria-labelledby="operation-title" aria-describedby="operation-description" ref={dialog} tabIndex={-1}>
   <div className="operation-icon"><Activity size={26}/><span className="operation-spinner" aria-hidden="true"/></div>
   <div className="eyebrow">{functional?'SIMULATED TEST IN PROGRESS':'OPERATION IN PROGRESS'}</div>
   <h2 id="operation-title">{aborting?'Stopping test…':title}</h2>
   <p id="operation-description">Please wait. Other controls are locked to prevent accidental input.</p>
   <div className="operation-status" role="status" aria-live="polite">{aborting?'Abort requested. Waiting for controller acknowledgement.':functional?'Verifying each operation and its contact feedback.':'Waiting for the operation to complete…'}</div>
   {functional&&<div className="operation-sequence">{['CLOSE','TRIP1','CLOSE','TRIP2'].map((command,i)=><div key={i} className={steps[i]?(steps[i].pass?'complete':'failed'):steps.length===i?'active':''}><span>{steps[i]?(steps[i].pass?<Check size={15}/>: '×'):steps.length===i?<span className="spinner"/>:i+1}</span><strong>{command}</strong><small>{steps[i]?(steps[i].pass?'Verified':'Failed'):steps.length===i?'Checking':'Waiting'}</small></div>)}</div>}
   {error&&<div className="operation-error" role="alert">{error}</div>}
   {canAbort&&<button className="btn danger" disabled={aborting} onClick={onAbort}><Square size={16}/>{aborting?'Stopping…':'Abort test'}</button>}
   <div className="operation-footnote">{canAbort?'Abort remains available. Closing this overlay with Escape is disabled.':'Controls unlock automatically when this operation finishes.'}</div>
 </div></div>,document.body);
}

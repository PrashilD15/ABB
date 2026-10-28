import {useEffect, useRef} from 'react';
import {createPortal} from 'react-dom';
import {Check, FileText, ShieldCheck} from 'lucide-react';
import './upload.css';

export function SchematicPreview({source, image=false, name='Uploaded schematic'}:{source:string;image?:boolean;name?:string}){
 return <section className="schematic-preview"><div className="preview-caption"><FileText size={17}/><strong>{name}</strong><span>Source drawing</span></div><div className="preview-document">{image?<img src={source} alt="Uploaded breaker schematic"/>:<iframe src={source} title="Uploaded breaker schematic"/>}</div></section>;
}

export function AnalysisOverlay({source,image,name,phase}:{source:string;image:boolean;name:string;phase:number}){
 const dialog=useRef<HTMLDivElement>(null);
 useEffect(()=>{
   const previous=document.activeElement as HTMLElement|null;
   const overflow=document.body.style.overflow;
   document.body.style.overflow='hidden';dialog.current?.focus();
   const block=(event:KeyboardEvent)=>{if(event.key==='Tab'||event.key==='Escape'){event.preventDefault();event.stopPropagation();}};
   document.addEventListener('keydown',block,true);
   return()=>{document.body.style.overflow=overflow;document.removeEventListener('keydown',block,true);previous?.focus();};
 },[]);
 return createPortal(<div className="analysis-backdrop"><div className="analysis-dialog" role="dialog" aria-modal="true" aria-labelledby="analysis-title" aria-describedby="analysis-description" tabIndex={-1} ref={dialog}>
   <div className="analysis-heading"><div className="analysis-emblem"><ShieldCheck size={24}/></div><div><div className="eyebrow">SCHEMATIC PROCESSING</div><h2 id="analysis-title">Uploading and verifying schematic</h2></div><span className="spinner"/></div>
   <p id="analysis-description">Please wait. Other controls are locked until analysis finishes. Your drawing is shown below.</p>
   <div className="analysis-progress" role="status" aria-live="polite">{['Uploading drawing','Understanding contacts with Gemini','Validating profile and capacity'].map((label,i)=><div key={label} className={i<phase?'finished':i===phase?'current':''}><span>{i<phase?<Check size={14}/>:i+1}</span><strong>{label}</strong>{i===phase&&<span className="spinner"/>}</div>)}</div>
   {source&&<div className="analysis-source" aria-hidden="true"><div className="analysis-filename"><FileText size={15}/>{name}</div>{image?<img src={source} alt=""/>:<iframe src={source} title="Schematic being verified" tabIndex={-1}/>}</div>}
   <div className="analysis-footer">No PLC programming or test command is sent during schematic analysis.</div>
 </div></div>,document.body);
}

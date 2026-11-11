#!/usr/bin/env node
/** Bounded real Chrome decoder gate, NOT native Plex/Jellyfin UI parity.
 * Imported only by the private browser harness. Video frame presentation, clock
 * advance and seek must succeed. HTTP200/206 alone cannot satisfy these checks.
 */
export async function decode(page, mediaPath, timeline=false, resumeSeconds=0) {
  if(!mediaPath.startsWith('/') || mediaPath.startsWith('//')) throw new Error('same-origin media required');
  return page.evaluate(async ({path,timeline,resumeSeconds})=>{
    const video=document.createElement('video');
    video.controls=true;video.muted=true;video.preload='auto';
    video.style.width='640px';document.body.replaceChildren(video);
    const events=[];
    for(const name of ['loadedmetadata','playing','seeking','seeked','error']) video.addEventListener(name,()=>events.push(name));
    function deadline(promise) {
      return Promise.race([promise,new Promise((_,reject)=>setTimeout(()=>reject(new Error('decoder deadline')),20000))]);
    }
    function once(name) {return new Promise((resolve,reject)=>{video.addEventListener(name,resolve,{once:true});video.addEventListener('error',()=>reject(new Error('decoder error')),{once:true});});}
    const metadata=once('loadedmetadata');video.src=path;
    await deadline(metadata);
    if(!Number.isFinite(video.duration) || video.duration<10 || video.videoWidth<1) throw new Error('expected new twelve-second video');
    if(!video.requestVideoFrameCallback) throw new Error('frame presentation API absent');
    if(resumeSeconds) {
      if(resumeSeconds<0 || resumeSeconds>=video.duration-1) throw new Error('invalid persisted resume position');
      const resumed=once('seeked');video.currentTime=resumeSeconds;await deadline(resumed);
    }
    let firstFrames;
    const presented=new Promise((resolve,reject)=>video.requestVideoFrameCallback((_,data)=>{if(resumeSeconds && data.mediaTime<resumeSeconds-0.35) return reject(new Error('persisted resume frame not decoded'));firstFrames=data.presentedFrames;resolve();}));
    await deadline(video.play());await deadline(presented);
    let activity=false;
    async function report(state,phase=state==='stopped'?'stop':'progress') {
      const at=video.currentTime;
      if(state==='playing' && (video.paused || video.ended)) throw new Error('not actually playing');
      const reply=await window.proofTimeline({state,phase,time:Math.floor(at*1000),duration:Math.floor(video.duration*1000)});
      if(state==='playing') {
        // The real video must STILL be advancing when activity returns. A delayed
        // callback after clip end is a failure, never manufactured playing proof.
        if(video.paused || video.ended || video.currentTime<=at) throw new Error('timeline outlived advancing video');
        activity ||= reply.active===true;
      } else if(reply.stopped!==true) throw new Error('stopped timeline failed');
    }
    if(timeline) await report('playing','start');
    const initial=video.currentTime;
    await deadline(new Promise(resolve=>{
      function tick(_,data) {if(video.currentTime>=initial+(resumeSeconds?0.25:1) && data.presentedFrames>firstFrames) resolve();else video.requestVideoFrameCallback(tick);}
      video.requestVideoFrameCallback(tick);
    }));
    if(timeline) await report('playing');
    if(resumeSeconds) {
      video.pause();if(timeline) await report('stopped');
      if(timeline && !activity) throw new Error('no actual resumed-session activity');
      return {duration:video.duration,resumed_from_seconds:resumeSeconds,stopped_seconds:video.currentTime,
        decoded_frames:video.getVideoPlaybackQuality().totalVideoFrames,timeline_activity_observed:activity,
        timeline_stopped:timeline,application_progress_proved:false,native_player_ui_proved:false,audio_output_proved:false};
    }
    video.pause();const before=video.currentTime;
    const seeked=once('seeked');video.currentTime=7;await deadline(seeked);
    if(Math.abs(video.currentTime-7)>0.35) throw new Error('seek failed');
    let seekFrame;
    const afterSeekFrame=new Promise(resolve=>video.requestVideoFrameCallback((_,data)=>{seekFrame=data.mediaTime;resolve();}));
    await deadline(video.play());await deadline(afterSeekFrame);
    if(seekFrame<6.5) throw new Error('seek did not decode target frame');
    await deadline(new Promise(resolve=>{
      function tick() {if(video.currentTime>=8) resolve();else video.requestVideoFrameCallback(tick);}
      video.requestVideoFrameCallback(tick);
    }));
    if(timeline) await report('playing');
    video.pause();
    if(timeline) {await report('stopped');if(!activity) throw new Error('no actual concurrent application activity');}
    const quality=video.getVideoPlaybackQuality();
    if(quality.totalVideoFrames<3) throw new Error('no decoded frames');
    return {duration:video.duration,width:video.videoWidth,height:video.videoHeight,
      before_seek_seconds:before,after_seek_seconds:video.currentTime,
      seek_frame_seconds:seekFrame,decoded_frames:quality.totalVideoFrames,
      dropped_frames:quality.droppedVideoFrames,events,
      timeline_activity_observed:activity,timeline_stopped:timeline,
      application_progress_proved:false,native_player_ui_proved:false,audio_output_proved:false};
  },{path:mediaPath,timeline,resumeSeconds});
}

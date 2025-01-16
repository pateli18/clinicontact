import { BarHeight, PhoneCallMetadata, SpeakerSegment } from "@/types";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "./ui/sheet";
import { AudioTranscriptDisplay } from "./audio/AudioTranscript";
import { useEffect, useRef, useState } from "react";
import {
  getAudioStreamUrl,
  getAudioTranscript,
  getPlayAudioUrl,
  hangUp,
  streamMetadata,
} from "@/utils/apiCalls";
import { toast } from "sonner";
import { LoadingView } from "./Loader";
import { AudioPlayer } from "./audio/AudioPlayer";
import { loadAndFormatDate } from "@/utils/dateFormat";
import { LiveAudioPlayer } from "./audio/LiveAudioPlayer";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerDescription,
  DrawerTitle,
} from "./ui/drawer";
import { useIsMobile } from "@/hooks/use-mobile";

const SheetView = (props: {
  children: React.ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
}) => {
  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent className="space-y-2 overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{props.title}</SheetTitle>
          <SheetDescription>{props.description}</SheetDescription>
        </SheetHeader>
        {props.children}
      </SheetContent>
    </Sheet>
  );
};

const DrawerView = (props: {
  children: React.ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
}) => {
  return (
    <Drawer open={props.open} onOpenChange={props.onOpenChange}>
      <DrawerContent className="h-[90%]">
        <DrawerHeader>
          <DrawerTitle>{props.title}</DrawerTitle>
          <DrawerDescription>{props.description}</DrawerDescription>
        </DrawerHeader>
        <div className="space-y-2 overflow-y-auto">{props.children}</div>
      </DrawerContent>
    </Drawer>
  );
};

export const CallDisplay = (props: {
  call: PhoneCallMetadata | null;
  setCall: (call: PhoneCallMetadata | null) => void;
}) => {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);
  const [transcriptLoading, setTranscriptLoading] = useState(true);
  const [audioTranscript, setAudioTranscript] = useState<{
    speaker_segments: SpeakerSegment[];
    bar_heights: BarHeight[];
    total_duration: number;
  }>({ speaker_segments: [], bar_heights: [], total_duration: 0 });
  const audioRef = useRef<HTMLAudioElement>(null);
  const [currentSegment, setCurrentSegment] = useState<SpeakerSegment | null>(
    null
  );
  useEffect(() => {
    if (!props.call) return;
    setOpen(true);
    setTranscriptLoading(true);
    getAudioTranscript(props.call.id).then((segments) => {
      if (segments !== null) {
        setAudioTranscript(segments);
      } else {
        toast.error("Failed to fetch audio transcript");
      }
      setTranscriptLoading(false);
    });
  }, [props.call?.id]);

  const onOpenChange = (open: boolean) => {
    if (!open) {
      props.setCall(null);
    }
    setOpen(open);
  };

  const title = "Call Audio";
  const description = props.call?.created_at
    ? loadAndFormatDate(props.call.created_at)
    : "";
  const components = (
    <>
      {transcriptLoading ? (
        <LoadingView text="Loading call..." />
      ) : (
        <div>
          {audioTranscript.speaker_segments.length > 0 && props.call && (
            <AudioPlayer
              audioUrl={getPlayAudioUrl(props.call.id)}
              audioRef={audioRef}
              setCurrentSegment={setCurrentSegment}
              speakerSegments={audioTranscript.speaker_segments}
              barHeights={audioTranscript.bar_heights}
              totalDuration={audioTranscript.total_duration}
            />
          )}
          <AudioTranscriptDisplay
            segments={audioTranscript.speaker_segments}
            audioRef={audioRef}
            currentSegment={currentSegment}
          />
        </div>
      )}
    </>
  );

  return isMobile ? (
    <DrawerView
      title={title}
      description={description}
      open={open}
      onOpenChange={onOpenChange}
    >
      {components}
    </DrawerView>
  ) : (
    <SheetView
      title={title}
      description={description}
      open={open}
      onOpenChange={onOpenChange}
    >
      {components}
    </SheetView>
  );
};

export const LiveCallDisplay = (props: {
  phoneCallId: string | null;
  setPhoneCallId: (phoneCallId: string | null) => void;
}) => {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);
  const [speakerSegments, setSpeakerSegments] = useState<SpeakerSegment[]>([]);
  const [currentSegment, setCurrentSegment] = useState<SpeakerSegment | null>(
    null
  );
  const audioRef = useRef<HTMLAudioElement>(null);
  const [callEnded, setCallEnded] = useState(false);

  const handleHangUp = async () => {
    if (!props.phoneCallId) return;
    const response = await hangUp(props.phoneCallId);
    if (response === false) {
      toast.error("Failed to hang up call, please try again");
    } else {
      toast.success("Hanging up call...");
    }
  };

  const runMetadataStream = async () => {
    if (!props.phoneCallId) return;
    try {
      for await (const payload of streamMetadata(props.phoneCallId)) {
        console.log(payload);
        if (payload.type === "call_end") {
          setCallEnded(true);
          break;
        } else {
          setSpeakerSegments(payload.data);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const onOpenChange = (open: boolean) => {
    if (!open) {
      props.setPhoneCallId(null);
      setSpeakerSegments([]);
      setCurrentSegment(null);
    }
    setOpen(open);
  };

  useEffect(() => {
    if (!props.phoneCallId) return;
    setOpen(true);

    // kick off streamingSpeakerSegments in the background
    (async () => {
      await runMetadataStream();
    })();
  }, [props.phoneCallId]);

  const title = "Live Call Audio";
  const description = "The audio will be a few seconds behind the actual call";
  const components = (
    <>
      {props.phoneCallId && (
        <div>
          <LiveAudioPlayer
            audioRef={audioRef}
            audioUrl={getAudioStreamUrl(props.phoneCallId)}
            speakerSegments={speakerSegments}
            setCurrentSegment={setCurrentSegment}
            handleHangUp={handleHangUp}
            callEnded={callEnded}
          />
          <AudioTranscriptDisplay
            segments={speakerSegments}
            currentSegment={currentSegment}
          />
        </div>
      )}
    </>
  );

  return isMobile ? (
    <DrawerView
      title={title}
      description={description}
      open={open}
      onOpenChange={onOpenChange}
    >
      {components}
    </DrawerView>
  ) : (
    <SheetView
      title={title}
      description={description}
      open={open}
      onOpenChange={onOpenChange}
    >
      {components}
    </SheetView>
  );
};

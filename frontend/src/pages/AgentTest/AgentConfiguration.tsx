import { HighlightedTextarea } from "@/components/HighlightedTextArea";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Agent } from "@/types";
import {
  getAgents,
  createNewAgentVersion,
  createAgent,
} from "@/utils/apiCalls";
import { loadAndFormatDate } from "@/utils/dateFormat";
import { PlusIcon, ReloadIcon } from "@radix-ui/react-icons";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useSearchParams } from "react-router-dom";
import { useAuthInfo } from "@propelauth/react";
import {
  Dialog,
  DialogTitle,
  DialogHeader,
  DialogContent,
  DialogTrigger,
} from "@/components/ui/dialog";

const CreateNewAgentModal = (props: {
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
  setAgentId: (agentId: { baseId: string; versionId: string } | null) => void;
}) => {
  const authInfo = useAuthInfo();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const handleCreateNewAgent = async (name: string) => {
    const response = await createAgent(name, authInfo.accessToken ?? null);
    if (response !== null) {
      props.setAgents((prev) => [response, ...prev]);
      props.setAgentId({
        baseId: response.base_id,
        versionId: response.id,
      });
      toast.success("Agent created");
      setOpen(false);
    } else {
      toast.error("Failed to create agent, please try again");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <PlusIcon className="w-4 h-4 mr-2" />
          Create New Agent
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create New Agent</DialogTitle>
        </DialogHeader>
        <Input
          placeholder="Enter New Agent Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Button
          disabled={name.length === 0}
          onClick={() => handleCreateNewAgent(name)}
        >
          Create
        </Button>
      </DialogContent>
    </Dialog>
  );
};

interface AgentConfigurationProps {
  agentId: {
    baseId: string;
    versionId: string;
  } | null;
  setAgentId: (agentId: { baseId: string; versionId: string } | null) => void;
  setSampleFields: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  agents: Agent[];
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
}

export const AgentConfiguration = (props: AgentConfigurationProps) => {
  const authInfo = useAuthInfo();
  const [saveLoading, setSaveLoading] = useState(false);
  const [newVersion, setNewVersion] = useState<Agent | null>(null);
  const activeAgent = props.agents.find(
    (agent) => agent.id === props.agentId?.versionId
  );

  useEffect(() => {
    if (activeAgent) {
      extractFields(activeAgent.system_message);
    }
  }, [activeAgent?.id]);

  const handleSaveVersion = async () => {
    if (newVersion) {
      setSaveLoading(true);
      const response = await createNewAgentVersion(
        newVersion.name,
        newVersion.system_message,
        newVersion.base_id,
        newVersion.active,
        authInfo.accessToken ?? null
      );
      setSaveLoading(false);
      if (response !== null) {
        props.setAgents((prev) => {
          const newAgents = [
            response,
            ...prev.map((agent) => ({ ...agent, active: false })),
          ];
          return newAgents;
        });
        props.setAgentId({
          baseId: response.base_id,
          versionId: response.id,
        });
        extractFields(response.system_message);
        setNewVersion(null);
        toast.success("Version saved");
      } else {
        toast.error("Failed to save version");
      }
    }
  };

  const extractFields = (value: string) => {
    // Extract all fields surrounded by {}
    const fields =
      value.match(/\{([^}]+)\}/g)?.map((field) => field.slice(1, -1)) || [];

    // Update sample fields
    props.setSampleFields((prev) => {
      const newFields: Record<string, string> = {};

      // Add fields in order of appearance, preserving existing values
      fields.forEach((field) => {
        newFields[field] = field in prev ? prev[field] : "";
      });

      return newFields;
    });
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div className="font-bold text-sm">Agent</div>
        <Select
          value={props.agentId?.baseId}
          onValueChange={(value) => {
            const agent = props.agents.find((agent) => agent.base_id === value);
            if (agent) {
              props.setAgentId({
                baseId: agent.base_id,
                versionId: agent.id,
              });
            }
          }}
        >
          <SelectTrigger
            disabled={props.agentId === null}
            className="truncate text-ellipsis"
          >
            <SelectValue placeholder="Select Agent" />
          </SelectTrigger>
          <SelectContent>
            <div className="overflow-y-scroll max-h-[200px]">
              {props.agents
                .filter((agent) => agent.active)
                .map((agent) => (
                  <SelectItem key={agent.base_id} value={agent.base_id}>
                    {agent.name}
                  </SelectItem>
                ))}
            </div>
          </SelectContent>
        </Select>
        <CreateNewAgentModal
          setAgents={props.setAgents}
          setAgentId={props.setAgentId}
        />
      </div>
      <div className="flex items-center gap-2">
        <div className="font-bold text-sm">Version</div>
        <Select
          value={props.agentId?.versionId}
          onValueChange={(value) => {
            const agent = props.agents.find(
              (agent) => agent.base_id === props.agentId?.baseId
            );
            if (agent) {
              props.setAgentId({
                baseId: agent.base_id,
                versionId: value,
              });
              setNewVersion(null);
            }
          }}
        >
          <SelectTrigger
            disabled={activeAgent === undefined}
            className="truncate text-ellipsis"
          >
            <SelectValue placeholder="Select Agent Version" />
          </SelectTrigger>
          <SelectContent>
            <div className="overflow-y-scroll max-h-[200px]">
              {props.agents
                .filter((agent) => agent.base_id === props.agentId?.baseId)
                .map((version) => (
                  <SelectItem key={version.id} value={version.id}>
                    <div className="flex space-x-2 items-center">
                      <div className="text-sm text-muted-foreground">
                        {loadAndFormatDate(version.created_at)}
                      </div>
                      {version.active && (
                        <Badge className="bg-green-500 text-white">
                          active
                        </Badge>
                      )}
                    </div>
                  </SelectItem>
                ))}
            </div>
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center gap-2">
        <div className="font-bold text-sm">Name</div>
        <Input
          placeholder="Enter Agent Name"
          value={(newVersion?.name ?? activeAgent?.name) || ""}
          onChange={(e) => {
            setNewVersion((prev) => {
              if (prev) {
                return {
                  ...prev,
                  name: e.target.value,
                };
              }
              return {
                ...activeAgent!,
                name: e.target.value,
              };
            });
          }}
          disabled={activeAgent === undefined}
        />
      </div>
      <div className="font-bold text-sm">Instructions</div>
      <HighlightedTextarea
        value={
          (newVersion?.system_message ?? activeAgent?.system_message) || ""
        }
        onChange={(value) => {
          setNewVersion((prev) => {
            if (prev) {
              return {
                ...prev,
                system_message: value,
              };
            }
            return {
              ...activeAgent!,
              system_message: value,
            };
          });
        }}
      />
      <div className="flex flex-wrap gap-2">
        {activeAgent?.document_metadata.map((document) => (
          <Badge variant="secondary" key={document.id}>
            {document.name}
          </Badge>
        ))}
      </div>
      {newVersion && (
        <Button onClick={handleSaveVersion}>
          Save Version
          {saveLoading && <ReloadIcon className="w-4 h-4 animate-spin" />}
        </Button>
      )}
    </div>
  );
};

/* Generated from api/contracts.py. Run npm run contracts:generate. */

export type Input = string;
export type Label = string;
export type ActionOptions = ActionOption[];
export type BalanceMilliPoints = number;
export type BalancePoints = string;
export type ChargedMilliPoints = number;
export type ChargedPoints = string;
export type InputTokens = number;
export type ModelCalls = number;
export type OutputTokens = number;
export type UsageCostMilliPoints = number;
export type Body = string;
export type CatalogId = string;
export type Complete = boolean;
export type Day = number | null;
export type GameId = string;
export type Id = string;
export type Kind = "choice" | "message" | "continue";
export type Label1 = string;
export type Enabled = boolean;
export type Id1 = string;
export type Label2 = string;
export type RequiresText = boolean;
export type Options = InteractionOption[];
export type Prompt = string;
export type Mode = "campaign" | "freeform";
export type Opening = string;
export type PresentationMode = "interactive" | "novel";
export type Kind1 = "narration" | "scene" | "dialogue" | "message" | "prompt" | "time";
export type SpeakerId = string;
export type SpeakerName = string;
export type Text = string;
export type Segments = StorySegment[];
export type StateVersion = number;
export type Id2 = string;
export type Label3 = string;
export type Max = number;
export type Min = number;
export type Value = string | number | boolean;
export type StatusFields = StatusField[];
export type Suggestions = string[];
export type Tick = number;
export type TimeOfDay = string | null;
export type TurnId = string | null;

export interface View {
  action_options: ActionOptions;
  billing?: TurnBilling;
  body: Body;
  catalog_id: CatalogId;
  complete: Complete;
  day: Day;
  game_id: GameId;
  interaction: Interaction | null;
  mode: Mode;
  opening: Opening;
  presentation_mode: PresentationMode;
  segments: Segments;
  state_version: StateVersion;
  status_fields: StatusFields;
  suggestions: Suggestions;
  tick: Tick;
  time_of_day: TimeOfDay;
  turn_id: TurnId;
}
export interface ActionOption {
  input: Input;
  label: Label;
}
export interface TurnBilling {
  balance_milli_points: BalanceMilliPoints;
  balance_points: BalancePoints;
  charged_milli_points: ChargedMilliPoints;
  charged_points: ChargedPoints;
  input_tokens: InputTokens;
  model_calls: ModelCalls;
  output_tokens: OutputTokens;
  usage_cost_milli_points: UsageCostMilliPoints;
}
export interface Interaction {
  id: Id;
  kind: Kind;
  label?: Label1;
  options: Options;
  prompt: Prompt;
}
export interface InteractionOption {
  enabled: Enabled;
  id: Id1;
  label: Label2;
  requires_text: RequiresText;
}
export interface StorySegment {
  kind: Kind1;
  speaker_id?: SpeakerId;
  speaker_name?: SpeakerName;
  text: Text;
}
export interface StatusField {
  id: Id2;
  label: Label3;
  max?: Max;
  min?: Min;
  value: Value;
}

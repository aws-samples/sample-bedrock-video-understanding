import { Component } from 'react';
import { Multiselect, ColumnLayout, Textarea, Slider, Select, Input, ExpandableSection, Container, Button, SpaceBetween } from '@cloudscape-design/components';
import FrameBasedConfig from '../../resources/frame-based-config.json'
import './videoFramePromptConfig.css';

class VideoFramePromptConfig extends Component {

    constructor(props) {
        super(props);
        this.state = {
            warnings: [],
            configs: [],
            
            // Current editing
            showEditConfig: false,
            currentEditingConfigId: null, // Track which config is being edited
            name: null,
            selectedPromptId: null,
            selectedPromptOptions: [],
            modelIdOption: null,
            prompt: null,
            toolConfig: null,

            sampleConfigs: [],
            models: [],

            maxTokens: FrameBasedConfig.default_max_tokens,
            topP: FrameBasedConfig.default_top_p,
            temperature: FrameBasedConfig.default_temperature
        }
    }   

    getConfigs() {
        // Configs are already auto-saved, just return them
        var configs = this.state.configs;
        
        // remove id and sourcePromptId fields
        configs = configs.map(({ id, sourcePromptId, ...rest }) => rest);
        return {
            configs: configs,
            warnings: []
        };
    }

    constructConfig() {

        var warns = [];
        if (this.state.name === null || this.state.name.length === 0) warns.push("Please input a name");
        if (this.state.prompt === null || this.state.prompt.length === 0) warns.push("Please input a prompt");

        // Check if name already exists
        if (this.state.configs && this.state.configs.find(c=>c.name == this.state.name)) {
            warns.push("Name already exists");
        }
        // Check if toolConfig is a valid JSON
        var config = null;
        if (this.state.toolConfig) {
            try {
                config = JSON.parse(this.state.toolConfig);
            } catch (e) {
                warns.push("Tool Configruation is not in valid JSON format");
            }
        }

        this.setState({warnings: warns});

        return {
            config:{
                id: crypto.randomUUID(),
                name: this.state.name,
                modelId: this.state.modelIdOption.value,
                prompt: this.state.prompt,
                toolConfig: config,
                inferConfig: {
                    maxTokens: this.state.maxTokens,
                    topP: this.state.topP,
                    temperature: this.state.temperature
                }
            }, 
            warnings: warns
        };
    }

    async componentDidMount() {
        const { selectedPromptId, sampleConfigs, models, promptConfigs } = this.props;
        this.setState({
            selectedPromptId: selectedPromptId?selectedPromptId : "default",
            sampleConfigs: sampleConfigs,
            models: models,
        },() => {
                this.setState({
                    modelIdOption: this.constructModelOption(models[0].value),
                    configs: promptConfigs?promptConfigs:[]
                });
                this.setFramePrompt(selectedPromptId);
            }
        );

        if (selectedPromptId) {
            
        }
    }

    constructModelOption(model_id) {
        const model = this.state.models.find(item => item.value === model_id);
        if (model)
            return {label: model.name, value: model.value};
        return null;
    }

    setFramePrompt(prompt_id) {
        const prompt = this.state.sampleConfigs.find(item=>item.id == prompt_id);
        if (prompt) {
            this.setState({
                selectedPromptId: prompt.id,
                name: prompt.name,
                modelIdOption: this.constructModelOption(prompt.model_id),
                prompt: prompt.prompt,
                toolConfig: prompt.toolConfig?JSON.stringify(prompt.toolConfig, null, 4):null
            })
        }
        return null;
    }

    updateConfigInList() {
        // Use setState with updater function to ensure we have the latest state
        this.setState((prevState) => {
            if (!prevState.currentEditingConfigId) return null;

            const configIndex = prevState.configs.findIndex(c => c.id === prevState.currentEditingConfigId);
            
            if (configIndex === -1) return null;
            
            const newConfigs = [...prevState.configs];
            let toolConfigParsed = null;
            
            if (prevState.toolConfig) {
                try {
                    toolConfigParsed = JSON.parse(prevState.toolConfig);
                } catch (e) {
                    // Invalid JSON, keep as null
                }
            }
            
            newConfigs[configIndex] = {
                ...newConfigs[configIndex],
                name: prevState.name,
                modelId: prevState.modelIdOption?.value,
                prompt: prevState.prompt,
                toolConfig: toolConfigParsed,
                inferConfig: {
                    maxTokens: prevState.maxTokens,
                    topP: prevState.topP,
                    temperature: prevState.temperature
                }
            };
            
            return { configs: newConfigs };
        });
    }

  render() {
    return  <div className="promptconfig">
                <div className="multiselect-container">
                    <Multiselect
                    selectedOptions={this.state.selectedPromptOptions}
                    onChange={({ detail }) => {
                        const previousOptions = this.state.selectedPromptOptions;
                        this.setState({ selectedPromptOptions: detail.selectedOptions });
                        
                        // Find newly selected prompts
                        const newlySelected = detail.selectedOptions.filter(
                            opt => !previousOptions.find(prev => prev.value === opt.value)
                        );
                        
                        // Find removed prompts
                        const removed = previousOptions.filter(
                            prev => !detail.selectedOptions.find(opt => opt.value === prev.value)
                        );
                        
                        // Auto-save all newly selected prompts to configs
                        if (newlySelected.length > 0) {
                            const newConfigs = [...this.state.configs];
                            
                            newlySelected.forEach(option => {
                                const prompt = this.state.sampleConfigs.find(item => item.id === option.value);
                                // Check if config already exists by sourcePromptId
                                if (prompt && !newConfigs.find(c => c.sourcePromptId === option.value)) {
                                    const config = {
                                        id: crypto.randomUUID(),
                                        sourcePromptId: option.value, // Track which prompt this came from
                                        name: prompt.name,
                                        modelId: prompt.model_id,
                                        prompt: prompt.prompt,
                                        toolConfig: prompt.toolConfig,
                                        inferConfig: {
                                            maxTokens: prompt.inferConfig?.maxTokens || this.state.maxTokens,
                                            topP: prompt.inferConfig?.topP || this.state.topP,
                                            temperature: prompt.inferConfig?.temperature || this.state.temperature
                                        }
                                    };
                                    newConfigs.push(config);
                                }
                            });
                            
                            this.setState({ configs: newConfigs });
                            
                            // Load the first newly selected prompt into the form for viewing
                            const firstNewOption = newlySelected[0];
                            const prompt = this.state.sampleConfigs.find(item => item.id === firstNewOption.value);
                            if (prompt) {
                                const savedConfig = newConfigs.find(c => c.sourcePromptId === firstNewOption.value);
                                this.setState({
                                    showEditConfig: true,
                                    currentEditingConfigId: savedConfig?.id,
                                    name: prompt.name,
                                    modelIdOption: this.constructModelOption(prompt.model_id),
                                    prompt: prompt.prompt,
                                    toolConfig: prompt.toolConfig ? JSON.stringify(prompt.toolConfig, null, 4) : null,
                                    maxTokens: prompt.inferConfig?.maxTokens || this.state.maxTokens,
                                    topP: prompt.inferConfig?.topP || this.state.topP,
                                    temperature: prompt.inferConfig?.temperature || this.state.temperature
                                });
                            }
                        }
                        
                        // Remove deselected prompts from configs
                        if (removed.length > 0) {
                            const removedPromptIds = removed.map(opt => opt.value);
                            const newConfigs = this.state.configs.filter(config => {
                                return !removedPromptIds.includes(config.sourcePromptId);
                            });
                            
                            // If we removed the currently editing config, hide the edit form
                            const removedCurrentConfig = removedPromptIds.includes(
                                this.state.configs.find(c => c.id === this.state.currentEditingConfigId)?.sourcePromptId
                            );
                            
                            this.setState({ 
                                configs: newConfigs,
                                showEditConfig: removedCurrentConfig ? false : this.state.showEditConfig,
                                currentEditingConfigId: removedCurrentConfig ? null : this.state.currentEditingConfigId
                            });
                        }
                        
                        // Hide controls if no options are selected
                        if (detail.selectedOptions.length === 0) {
                            this.setState({ 
                                showEditConfig: false,
                                currentEditingConfigId: null
                            });
                        }
                    }}
                    options={this.state.sampleConfigs?.map(item => ({
                        label: item.name,
                        value: item.id
                    }))}
                    placeholder="Add a new prompt"
                    filteringType="auto"
                    hideTokens={true}
                    />
                    {this.state.selectedPromptOptions.length > 0 && (
                        <div style={{ marginTop: '10px' }}>
                            <SpaceBetween direction="horizontal" size="xs">
                                {this.state.selectedPromptOptions.map((option, index) => {
                                    // Find config by sourcePromptId
                                    const savedConfig = this.state.configs.find(c => c.sourcePromptId === option.value);
                                    
                                    // Display the current saved name, not the original option label
                                    const displayLabel = savedConfig ? savedConfig.name : option.label;
                                    
                                    return (
                                        <div key={option.value} className="token-item">
                                            <Button
                                                variant="inline-link"
                                                onClick={() => {
                                                    if (savedConfig) {
                                                        this.setState({
                                                            showEditConfig: true,
                                                            currentEditingConfigId: savedConfig.id,
                                                            name: savedConfig.name,
                                                            modelIdOption: this.constructModelOption(savedConfig.modelId),
                                                            prompt: savedConfig.prompt,
                                                            toolConfig: savedConfig.toolConfig ? JSON.stringify(savedConfig.toolConfig, null, 4) : null,
                                                            maxTokens: savedConfig.inferConfig?.maxTokens || this.state.maxTokens,
                                                            topP: savedConfig.inferConfig?.topP || this.state.topP,
                                                            temperature: savedConfig.inferConfig?.temperature || this.state.temperature
                                                        });
                                                    }
                                                }}
                                            >
                                                {displayLabel}
                                            </Button>
                                            <Button
                                                iconName="close"
                                                variant="inline-icon"
                                                onClick={() => {
                                                    const newOptions = [...this.state.selectedPromptOptions];
                                                    newOptions.splice(index, 1);
                                                    
                                                    // Check if we're removing the currently editing config
                                                    const removingCurrentConfig = savedConfig && savedConfig.id === this.state.currentEditingConfigId;
                                                    
                                                    this.setState({ selectedPromptOptions: newOptions });
                                                    
                                                    // Remove from configs by sourcePromptId
                                                    if (savedConfig) {
                                                        const newConfigs = this.state.configs.filter(config => config.sourcePromptId !== option.value);
                                                        this.setState({ 
                                                            configs: newConfigs,
                                                            // Hide controls if we removed the current config or if no options left
                                                            showEditConfig: (removingCurrentConfig || newOptions.length === 0) ? false : this.state.showEditConfig,
                                                            currentEditingConfigId: (removingCurrentConfig || newOptions.length === 0) ? null : this.state.currentEditingConfigId
                                                        });
                                                    }
                                                }}
                                            />
                                        </div>
                                    );
                                })}
                            </SpaceBetween>
                        </div>
                    )}
                </div>
                <br/>
                {this.state.warnings.length > 0 && this.state.warnings.map(w=> {return <div className='warnings'>{w}</div>})}
                {this.state.showEditConfig &&
                <div className='prompt'>
                    <div className='label'>Display name</div>
                    <Input value={this.state.name} onChange={
                        ({detail})=> {
                            this.setState({name: detail.value}, () => this.updateConfigInList());
                        }
                    }></Input>
                    <div className='label'>Select a model</div>
                    <Select selectedOption={this.state.modelIdOption}
                        onChange={({ detail }) => {
                            this.setState({modelIdOption: detail.selectedOption}, () => this.updateConfigInList());
                        }}
                        options={this.state.models.map(item => {
                            return {
                                label: item.name,
                                value: item.value,
                            };
                        })} />
                    <div className='label'>Input a prompt</div>
                    <Textarea rows={4} value={this.state.prompt} onChange={
                        ({detail})=>{
                                this.setState({
                                    prompt: detail.value,
                                }, () => this.updateConfigInList());
                        }                                                
                    }></Textarea>
                    <ExpandableSection headerText="Tool Configuration">
                        <Textarea rows={10} onChange={({ detail }) => {
                            this.setState({toolConfig: detail.value}, () => this.updateConfigInList());
                        }} value={this.state.toolConfig}></Textarea>
                    </ExpandableSection>
                    <br/>
                    <ExpandableSection headerText="Inference Configuration">
                        <ColumnLayout columns={3}>
                            <Container>
                                <div className='label'>Maximum Output Tokens</div>
                                <Slider
                                    onChange={({ detail }) => {
                                        this.setState({maxTokens: detail.value}, () => this.updateConfigInList());
                                    }}
                                    value={this.state.maxTokens}
                                    max={32000}
                                    min={0}
                                    step={1}
                                    />                            
                            </Container>
                            <Container>
                                <div className='label'>Top P</div>
                                <Slider
                                    onChange={({ detail }) => {
                                        this.setState({topP: detail.value}, () => this.updateConfigInList());
                                    }}
                                    value={this.state.topP}
                                    max={1}
                                    min={0}
                                    step={0.1}
                                    />                            
                            </Container>
                            <Container>
                                <div className='label'>Temperature</div>
                                <Slider
                                    onChange={({ detail }) => {
                                        this.setState({temperature: detail.value}, () => this.updateConfigInList());
                                    }}
                                    value={this.state.temperature}
                                    max={1}
                                    min={0}
                                    step={0.1}
                                    />                            
                            </Container>

                        </ColumnLayout>
                    </ExpandableSection>

                </div>}
            </div>
  };
};
export default VideoFramePromptConfig;
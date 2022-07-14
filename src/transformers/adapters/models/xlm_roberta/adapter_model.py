from ....models.xlm_roberta.modeling_xlm_roberta import XLM_ROBERTA_START_DOCSTRING, XLMRobertaConfig
from ....utils import add_start_docstrings
from ..roberta.adapter_model import RobertaAdapterModel, RobertaModelWithHeads
import numpy as np
import torch
import copy


@add_start_docstrings(
    """XLM-RoBERTa Model with the option to add multiple flexible heads on top.""",
    XLM_ROBERTA_START_DOCSTRING,
)
class XLMRobertaAdapterModel(RobertaAdapterModel):
    """
    This class overrides :class:`~transformers.RobertaAdapterModel`. Please check the superclass for the appropriate
    documentation alongside usage examples.
    """

    config_class = XLMRobertaConfig

    def __init__(self, config):
        super().__init__(config)
        # source language is English
        self.src_lang = 'en'
        # layers to project
        # should be a single layer for series projection
        # could be a list of layers for parallel projection
        self.proj_layers = [] * (self.config.num_hidden_layers+1)


    def activate_embedding_projection(self):
        if not self.roberta.encoder.embedding_projection_flag:
            elf.roberta.encoder.embedding_projection_flag = True

    def activate_layer_projections(self, layers: list):
        for layer_i in layers:
            if not self.roberta.encoder.layer[layer_i].projection_flag:
                self.roberta.encoder.layer[layer_i].projection_flag = True


    def disable_embedding_projection(self):
        if self.roberta.encoder.embedding_projection_flag:
            elf.roberta.encoder.embedding_projection_flag = False

    def disable_layer_projections(self, layers: list):
        for layer_i in layers:
            if self.roberta.encoder.layer[layer_i].projection_flag:
                self.roberta.encoder.layer[layer_i].projection_flag = False


    def load_projections(self, lang_list: list, subspace_dir: str):
        if subspace_dir[-1] != '/': subspace_dir += '/'

        variance_accounted = 0.9

        # compute projections
        projection_dict = {}
        means_a_dict = {}
        means_b_dict = {}

        for lang in lang_list:

            projections = []
            means_a = []
            means_b = []

            num_layers = self.roberta.config.num_hidden_layers
            dim_size = self.roberta.config.hidden_size

            for layer_i in range(self.config.num_hidden_layers+1):
                mean_a = np.load(subspace_dir+self.src_lang+'_layer'+str(layer_i)+'_mean.npy') # change for other projections
                mean_b = np.load(subspace_dir+self.src_lang+'_layer'+str(layer_i)+'_mean.npy') # change for other projections

                means_a.append(mean_a)
                means_b.append(mean_b)

                s = np.load(subspace_dir+lang+'_layer'+str(layer_i)+'_s.npy')
                vh = np.load(subspace_dir+lang+'_layer'+str(layer_i)+'_vh.npy')
                subspace_m = np.load(subspace_dir+lang+'_layer'+str(layer_i)+'_mean.npy')

                v = np.transpose(vh) # columns of V form the desired orthonormal basis

                subspace_dim = 0
                s_squared = np.square(s)
                total_variance = np.sum(s_squared) # Proportional to total variance.
                cutoff_variance = variance_accounted * total_variance
                curr_variance = 0.0
                for i in range(s.shape[-1]):
                    curr_variance += s_squared[i]
                    if curr_variance >= cutoff_variance:
                        subspace_dim = i+1
                        break
                # Projection matrix: convert into basis (excluding some dimensions), then
                # convert back into standard basis.
                v = v[:, :subspace_dim]
                projection_matrix = np.matmul(v, np.transpose(v))
                projections.append(projection_matrix)

                projection_dict[lang] = projections
                means_a_dict[lang] = means_a
                means_b_dict[lang] = means_b

        self.set_layer_projections(projection_dict, lang_list, means_a_dict, means_b_dict)


    def set_layer_projections(self, projection_dict, lang_list, means_a_dict, means_b_dict):
        for lang in lang_list:
            projection, projection_shift = self.compute_projection(projection_dict, means_a_dict, means_b_dict, lang, 0) # 0 for embedding layer projections
            self.roberta.encoder.embedding_projections[lang] = copy.deepcopy(projection)
            self.roberta.encoder.embedding_projections_shifts[lang] = copy.deepcopy(projection_shift)
            # add shifts here

        for lang in lang_list:
            for layer_i in range(1, self.config.num_hidden_layers+1):
                projection, projection_shift = self.compute_projection(projection_dict, means_a_dict, means_b_dict, lang, layer_i)
                self.roberta.encoder.layer[layer_i-1].layer_projections[lang] = copy.deepcopy(projection)
                self.roberta.encoder.layer[layer_i-1].layer_projections_shifts[lang] = copy.deepcopy(projection_shift)
                # add shifts here


    def compute_projection(self, projection_dict, means_a_dict, means_b_dict, lang, layer_i):
        dim_size = self.config.hidden_size
        projection = torch.tensor(projection_dict[lang][layer_i]).float() 
        mean_a = torch.tensor(means_a_dict[lang][layer_i]).float()
        mean_b = torch.tensor(means_b_dict[lang][layer_i]).float()
        projection_shift = mean_b - torch.matmul(projection, mean_a)
        projection_shift = projection_shift.reshape(1, 1, dim_size)
        return projection, projection_shift


@add_start_docstrings(
    """XLM-RoBERTa Model with the option to add multiple flexible heads on top.""",
    XLM_ROBERTA_START_DOCSTRING,
)
class XLMRobertaModelWithHeads(RobertaModelWithHeads):
    """
    This class overrides :class:`~transformers.RobertaModelWithHeads`. Please check the superclass for the appropriate
    documentation alongside usage examples.
    """

    config_class = XLMRobertaConfig

from functools import partial
from lasagne.layers import dnn
from application.luna import LunaDataLoader, OnlyPositiveLunaDataLoader, BcolzLunaDataLoader
from application.preprocessors.in_the_middle import PutInTheMiddle
from application.preprocessors.lio_augmentation import LioAugment, LioAugmentOnlyPositive
from configurations.default import *

import lasagne
import theano.tensor as T
import numpy as np

from application.objectives import CrossEntropyObjective, WeightedSegmentationCrossEntropyObjective, \
    JaccardIndexObjective, SoerensonDiceCoefficientObjective, RecallObjective, PrecisionObjective, ClippedFObjective
from application.data import PatientDataLoader
from deep_learning.upscale import Upscale3DLayer
from interfaces.data_loader import VALIDATION, TRAINING, TEST, TRAIN
from deep_learning.deep_learning_layers import ConvolutionLayer, PoolLayer

#####################
#   running speed   #
#####################
from interfaces.preprocess import NormalizeInput, ZMUV

"This is the number of samples in each batch"
batch_size = 1
"This is the number of batches in each chunk. Computation speeds up if this is as big as possible." \
"However, when too big, the GPU will run out of memory"
batches_per_chunk = 32
"Reload the parameters from last time and continue, or start anew when you run this config file again"
restart_from_save = False
"After how many chunks should you save parameters. Keep this number high for better performance. It will always store at end anyway"
save_every_chunks = 50


#####################
#   preprocessing   #
#####################

IMAGE_SIZE = 64

AUGMENTATION_PARAMETERS = {
    "scale": [1, 1, 1],  # factor
    "rotation": [180, 180, 180],  # degrees (from -180 to 180)
    "shear": [0, 0, 0],  # degrees
    "translation": [64, 64, 64],  # mms (from -128 to 128)
    "reflection": [0, 0, 0] #Bernoulli p
}

"Put in here the preprocessors for your data." \
"They will be run consequently on the datadict of the dataloader in the order of your list."
preprocessors = [
    LioAugmentOnlyPositive(tags=["luna:3d", "luna:segmentation"],
               output_shape=(IMAGE_SIZE,IMAGE_SIZE,IMAGE_SIZE),  # in pixels
               norm_patch_size=(IMAGE_SIZE,IMAGE_SIZE,IMAGE_SIZE),  # in mms
               augmentation_params=AUGMENTATION_PARAMETERS
               ),
    ZMUV("luna:3d", bias =  -648.59027, std = 679.21021),
]

#####################
#     training      #
#####################
"This is the train dataloader. We will train until this one stops loading data."
"You can set the number of epochs, the datasets and if you want it multiprocessed"
training_data = BcolzLunaDataLoader(
    only_positive=True,
    sets=TRAINING,
    epochs=10,
    preprocessors=preprocessors,
    multiprocess=False,
    crash_on_exception=True,
)

"Schedule the reducing of the learning rate. On indexing with the number of epochs, it should return a value for the learning rate."
learning_rate_schedule = {
    0.0: 0.00001,
    8.0: 0.000001,
    9.0: 0.0000001,
}
"The function to build updates."
build_updates = lasagne.updates.adam


#####################
#    validation     #
#####################
"We do our validation after every x epochs of training, and at the end"
epochs_per_validation = 1

"Which data do we want to validate on. We will run all validation objectives on each validation data set."
validation_data = {
    "validation set": BcolzLunaDataLoader(
        only_positive=True,
        sets=VALIDATION,
        epochs=1,
        preprocessors=preprocessors,
        process_last_chunk=True,
        multiprocess=True,
        crash_on_exception=True,
    ),
    "training set": BcolzLunaDataLoader(
        only_positive=True,
        sets=TRAINING,
        epochs=0.01,
        preprocessors=preprocessors,
        process_last_chunk=True,
        multiprocess=True,
        crash_on_exception=True,
    ),
}


#####################
#      testing      #
#####################
"This is the data which will be used for testing."
test_data = None


#####################
#     debugging     #
#####################

"Here we return a dict with the Theano objectives we are interested in. Both for the train and validation set."
"On both sets, you may request multiple objectives! Only the one called 'objective' is used to optimize on."

def build_objectives(interface_layers):
    obj_weighted = WeightedSegmentationCrossEntropyObjective(
        classweights=[10000, 1],
        input_layer=interface_layers["outputs"]["predicted_segmentation"],
        target_name="luna:segmentation",
    )

    obj_jaccard = JaccardIndexObjective(
        smooth=1e-5,
        input_layer=interface_layers["outputs"]["predicted_segmentation"],
        target_name="luna:segmentation",
    )

    obj_dice = SoerensonDiceCoefficientObjective(
        smooth=1e-5,
        input_layer=interface_layers["outputs"]["predicted_segmentation"],
        target_name="luna:segmentation",
    )

    obj_precision = PrecisionObjective(
        smooth=1e-5,
        input_layer=interface_layers["outputs"]["predicted_segmentation"],
        target_name="luna:segmentation",
    )

    obj_recall = RecallObjective(
        smooth=1e-5,
        input_layer=interface_layers["outputs"]["predicted_segmentation"],
        target_name="luna:segmentation",
    )

    obj_custom = ClippedFObjective(
        smooth=1e-5,
        recall_weight = 1./0.95,
        precision_weight = 1./0.3,
        input_layer=interface_layers["outputs"]["predicted_segmentation"],
        target_name="luna:segmentation",
    )

    return {
        "train":{
            "objective": obj_dice,
            "jaccard": obj_jaccard,
            "weighted": obj_weighted,
            "Dice": obj_dice,
            "precision": obj_precision,
            "recall": obj_recall,
        },
        "validate":{
            "objective": obj_dice,
            "jaccard": obj_jaccard,
            "weighted": obj_weighted,
            "Dice": obj_dice,
            "precision": obj_precision,
            "recall": obj_recall,
        }
    }

#################
# Regular model #
#################


"For ease of working, we predefine some layers with their parameters"
conv3d = partial(dnn.Conv3DDNNLayer,
                 filter_size=3,
                 pad='same',
                 W=lasagne.init.Orthogonal('relu'),
                 b=lasagne.init.Constant(0.0),
                 nonlinearity=lasagne.nonlinearities.rectify)

max_pool3d = partial(dnn.MaxPool3DDNNLayer,
                     pool_size=2)

"Here we build a model. The model returns a dict with the requested inputs for each layer:" \
"And with the outputs it generates. You may generate multiple outputs (for analysis or for some other objectives, etc)" \
"Unused outputs don't cost in performance"
def build_model():
    l_in = lasagne.layers.InputLayer(shape=(None,IMAGE_SIZE,IMAGE_SIZE,IMAGE_SIZE))

    l0 = lasagne.layers.DimshuffleLayer(l_in, pattern=[0,'x',1,2,3])

    net = {}
    base_n_filters = 256
    net['contr_1_1'] = conv3d(l0, base_n_filters)
    net['contr_1_2'] = conv3d(net['contr_1_1'], base_n_filters)
    net['pool1'] = max_pool3d(net['contr_1_2'])

    net['contr_2_1'] = conv3d(net['pool1'], base_n_filters * 2)
    net['contr_2_2'] = conv3d(net['contr_2_1'], base_n_filters * 2)

    net['expand_3_1'] = conv3d(net['contr_2_2'], base_n_filters * 2)
    net['expand_3_2'] = conv3d(net['expand_3_1'], base_n_filters * 2)
    net['upscale4'] = Upscale3DLayer(net['expand_3_2'], 2)

    net['concat4'] = lasagne.layers.ConcatLayer([net['upscale4'], net['contr_1_2']],
                                           cropping=(None, None, "center", "center", "center"))
    net['expand_4_1'] = conv3d(net['concat4'], base_n_filters)
    net['expand_4_2'] = conv3d(net['expand_4_1'], base_n_filters)

    net['output_segmentation'] = dnn.Conv3DDNNLayer(net['expand_4_2'], num_filters=1,
                                                    filter_size=1,
                                                    W=lasagne.init.Constant(0),
                                                    b=None,
                                                    nonlinearity=lasagne.nonlinearities.sigmoid)

    l_out = lasagne.layers.SliceLayer(net['output_segmentation'], indices=0, axis=1)

    return {
        "inputs":{
            "luna:3d": l_in,
        },
        "outputs": {
            "predicted_segmentation": l_out
        },
    }
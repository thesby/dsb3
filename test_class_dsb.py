import string
import sys
import lasagne as nn
import numpy as np
import theano
import utils
import logger
import buffering
from configuration import config, set_configuration
import pathfinder
import utils_lung
import os
import evaluate_submission

theano.config.warn_float64 = 'raise'

if len(sys.argv) < 2:
    sys.exit("Usage: test_class_dsb.py <configuration_name> <valid|test>")

config_name = sys.argv[1]
set_configuration('configs_class_dsb', config_name)

set = sys.argv[2] if len(sys.argv) == 3 else 'test'

# metadata
metadata_dir = utils.get_dir_path('models', pathfinder.METADATA_PATH)
metadata_path = utils.find_model_metadata(metadata_dir, config_name)

metadata = utils.load_pkl(metadata_path)
expid = metadata['experiment_id']

# logs
logs_dir = utils.get_dir_path('logs', pathfinder.METADATA_PATH)
sys.stdout = logger.Logger(logs_dir + '/%s-%s.log' % (expid, set))
sys.stderr = sys.stdout

# predictions path
predictions_dir = utils.get_dir_path('model-predictions', pathfinder.METADATA_PATH, no_name=True)
output_pkl_file = predictions_dir + '/%s-%s.pkl' % (expid, set)

submissions_dir = utils.get_dir_path('submissions', pathfinder.METADATA_PATH, no_name=True)
output_csv_file = submissions_dir + '/%s-%s.csv' % (expid, set)

# if os.path.isfile(output_pkl_file):
#     pid2prediction = utils.load_pkl(output_pkl_file)
#     utils_lung.write_submission(pid2prediction, output_csv_file)
#     print 'saved csv'
#     print output_csv_file
#     sys.exit(0)

print 'Build model'
model = config().build_model()
all_layers = nn.layers.get_all_layers(model.l_out)
all_params = nn.layers.get_all_params(model.l_out)
num_params = nn.layers.count_params(model.l_out)
print '  number of parameters: %d' % num_params
print string.ljust('  layer output shapes:', 36),
print string.ljust('#params:', 10),
print 'output shape:'
for layer in all_layers:
    name = string.ljust(layer.__class__.__name__, 32)
    num_param = sum([np.prod(p.get_value().shape) for p in layer.get_params()])
    num_param = string.ljust(num_param.__str__(), 10)
    print '    %s %s %s' % (name, num_param, layer.output_shape)

nn.layers.set_all_param_values(model.l_out, metadata['param_values'])

# theano functions
iter_test = theano.function([model.l_in.input_var], nn.layers.get_output(model.l_out, deterministic=True))

if set == 'test':
    if pathfinder.STAGE == 1:
        pid2label = utils_lung.read_test_labels(pathfinder.TEST_LABELS_PATH)
        data_iterator = config().test_data_iterator
    else:
        output_pkl_file = predictions_dir + '/%s-%s.pkl' % (expid, "stage2")
        output_csv_file = submissions_dir + '/%s-%s.csv' % (expid, "stage2")
        test_pids = utils.load_pkl(pathfinder.VALIDATION_SPLIT_PATH)["test_stage2"]
        print "nsamples test_stage2", len(test_pids)

        data_iterator = config().data_iterators.DSBPatientsDataGenerator(data_path=pathfinder.DATA_PATH,
                                                                     batch_size=1,
                                                                     transform_params=config().p_transform,
                                                                     n_candidates_per_patient=config().n_candidates_per_patient,
                                                                     data_prep_fun=config().data_prep_function_valid,
                                                                     id2candidates_path=config().id2candidates_path,
                                                                     rng=config().rng,
                                                                     patient_ids=test_pids,
                                                                     random=False, infinite=False)
    print
    print 'Data'
    print 'n test: %d' % data_iterator.nsamples

    pid2prediction = {}
    for i, (x_test, _, id_test) in enumerate(buffering.buffered_gen_threaded(
            data_iterator.generate())):
        predictions = iter_test(x_test)
        pid = id_test[0]
        pid2prediction[pid] = predictions[0, 1] if predictions.shape[-1] == 2 else predictions[0]
        print i, pid, predictions


    utils.save_pkl(pid2prediction, output_pkl_file)
    print 'Saved test predictions into pkl', os.path.basename(output_pkl_file)

    if pathfinder.STAGE == 1:
        test_loss = utils_lung.evaluate_log_loss(pid2prediction, pid2label)
        print 'Test loss', test_loss

    utils_lung.write_submission(pid2prediction, output_csv_file)
    print 'Saved predictions into csv'

    if pathfinder.STAGE == 1:
        loss = evaluate_submission.leaderboard_performance(output_csv_file)
        print loss

elif set == 'newsplit':
    pid2label = utils_lung.read_test_labels(pathfinder.MIXED_SPLIT_PATH)["test"]
    data_iterator = config().test_data_iterator

    print
    print 'Data'
    print 'n test: %d' % data_iterator.nsamples

    pid2prediction = {}
    for i, (x_test, _, id_test) in enumerate(buffering.buffered_gen_threaded(
            data_iterator.generate())):
        predictions = iter_test(x_test)
        pid = id_test[0]
        pid2prediction[pid] = predictions[0, 1] if predictions.shape[-1] == 2 else predictions[0]
        print i, pid, predictions, pid2label[pid]

    utils.save_pkl(pid2prediction, output_pkl_file)
    print 'Saved validation predictions into pkl', os.path.basename(output_pkl_file)

    test_loss = utils_lung.evaluate_log_loss(pid2prediction, pid2label)
    print 'Test loss', test_loss

    utils_lung.write_submission(pid2prediction, output_csv_file)
    print 'Saved predictions into csv'
    loss = evaluate_submission.leaderboard_performance(output_csv_file)
    print loss

elif set == 'stage2':
    data_iterator = config().test_data_iterator

    print
    print 'Data'
    print 'n test: %d' % data_iterator.nsamples

    pid2prediction = {}
    for i, (x_test, _, id_test) in enumerate(buffering.buffered_gen_threaded(data_iterator.generate())):
        predictions = iter_test(x_test)
        pid = id_test[0]
        pid2prediction[pid] = predictions[0, 1] if predictions.shape[-1] == 2 else predictions[0]
        print i, pid, predictions

    utils.save_pkl(pid2prediction, output_pkl_file)
    print 'Saved validation predictions into pkl', os.path.basename(output_pkl_file)

    utils_lung.write_submission(pid2prediction, output_csv_file)
    print 'Saved predictions into csv'

elif set == 'valid':
    data_iterator = config().valid_data_iterator

    print
    print 'Data'
    print 'n valid: %d' % data_iterator.nsamples

    pid2prediction, pid2label = {}, {}
    for i, (x_test, y_test, id_test) in enumerate(buffering.buffered_gen_threaded(
            data_iterator.generate())):
        predictions = iter_test(x_test)
        pid = id_test[0]
        pid2prediction[pid] = predictions[0, 1] if predictions.shape[-1] == 2 else predictions[0]
        pid2label[pid] = y_test[0]
        print i, pid, predictions, pid2label[pid]

    utils.save_pkl(pid2prediction, output_pkl_file)
    print 'Saved validation predictions into pkl', os.path.basename(output_pkl_file)
    valid_loss = utils_lung.evaluate_log_loss(pid2prediction, pid2label)
    print 'Validation loss', valid_loss
elif set == 'train':
    data_iterator = config().train_data_iterator
    data_iterator.batch_size = 1
    if hasattr(data_iterator, "random"): data_iterator.random = False
    if hasattr(data_iterator, "infinite"): data_iterator.infinite = False
    if hasattr(data_iterator, "data_prep_fun"): data_iterator.data_prep_fun = config().data_prep_function_valid

    print
    print 'Data'
    print 'n train: %d' % data_iterator.nsamples

    pid2prediction, pid2label = {}, {}
    for i, (x_test, y_test, id_test) in enumerate(buffering.buffered_gen_threaded(
            data_iterator.generate())):
        predictions = iter_test(x_test)
        pid = id_test[0]
        pid2prediction[pid] = predictions[0, 1] if predictions.shape[-1] == 2 else predictions[0]
        pid2label[pid] = y_test[0]
        print i, pid, predictions, pid2label[pid]

    utils.save_pkl(pid2prediction, output_pkl_file)
    print 'Saved training predictions into pkl', os.path.basename(output_pkl_file)
    train_loss = utils_lung.evaluate_log_loss(pid2prediction, pid2label)
    print 'Training loss', train_loss
else:
    raise ValueError('wrong set argument')
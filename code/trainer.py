"""Script for training language models."""
import argparse
import logging
import os
import pandas
import time
import numpy as np
import tensorflow as tf

import helper
from dataset import Dataset, LoadData
from model import Model
from metrics import MovingAvg
from vocab import Vocab

parser = argparse.ArgumentParser()
parser.add_argument('expdir', help='experiment directory')
parser.add_argument('--params', type=str, default='default_params.json',
                    help='json file with hyperparameters')
parser.add_argument('--data', type=str, action='append', dest='data',
                    help='where to load the data from')
parser.add_argument('--valdata', type=str, action='append', dest='valdata',
                    help='where to load validation data', default=[])
parser.add_argument('--threads', type=int, default=12,
                    help='how many threads to use in tensorflow')
args = parser.parse_args()

expdir = args.expdir
if not os.path.exists(expdir):
  os.mkdir(expdir)
# else:
#   print('ERROR: expdir already exists')
#   exit(-1)


tf.set_random_seed(int(time.time() * 1000))

params = helper.GetParams(args.params, 'train', args.expdir)


logging.basicConfig(filename=os.path.join(expdir, 'logfile.txt'),
                    level=logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler())


print("Load Dataset")
df = LoadData(args.data)

print("char vocab save")
char_vocab = Vocab.MakeFromData(df.query_, min_count=10)
char_vocab.Save(os.path.join(args.expdir, 'char_vocab.pickle'))

params.vocab_size = len(char_vocab)
user_vocab = Vocab.MakeFromData([[u] for u in df.user], min_count=15)
user_vocab.Save(os.path.join(args.expdir, 'user_vocab.pickle'))
params.user_vocab_size = len(user_vocab)
dataset = Dataset(df, char_vocab, user_vocab, max_len=params.max_len,
                  batch_size=params.batch_size)


val_df = LoadData(args.valdata)
valdata = Dataset(val_df, char_vocab, user_vocab, max_len=params.max_len,
                  batch_size=params.batch_size)


print("Load Model Config")
model = Model(params)
saver = tf.train.Saver(tf.global_variables())
config = tf.ConfigProto(inter_op_parallelism_threads=args.threads,
                        intra_op_parallelism_threads=args.threads)
session = tf.Session(config=config)
session.run(tf.global_variables_initializer())


avg_loss = MovingAvg(0.97)  # exponential moving average of the training loss
for idx in range(params.iters):
  feed_dict = dataset.GetFeedDict(model)
  feed_dict[model.dropout_keep_prob] = params.dropout

  c, _ = session.run([model.avg_loss, model.train_op], feed_dict)
  cc = avg_loss.Update(c)
  if idx % 50 == 0 and idx > 0:
    # test one batch from the validation set
    val_c = session.run(model.avg_loss, valdata.GetFeedDict(model))
    logging.info({'iter': idx, 'cost': cc, 'rawcost': c,
                  'valcost': val_c})
  if idx % 2000 == 0:  # save a model file every 2,000 minibatches
    saver.save(session, os.path.join(expdir, 'model.bin'),
               write_meta_graph=False)

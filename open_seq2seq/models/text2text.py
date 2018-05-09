# Copyright (c) 2017 NVIDIA Corporation
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals
from six.moves import range

import nltk
import re
import codecs

from .seq2seq import Seq2Seq
from open_seq2seq.data.text2text import SpecialTextTokens
from open_seq2seq.utils.utils import deco_print, array_to_string, \
                                     text_ids_to_string


def transform_for_bleu(row, vocab, ignore_special=False,
                       delim=' ', bpe_used=False):
  n = len(vocab)
  if ignore_special:
    f_row = []
    for i in range(0, len(row)):
      char_id = row[i]
      if char_id == SpecialTextTokens.EOS_ID.value:
        break
      if char_id != SpecialTextTokens.PAD_ID.value and \
         char_id != SpecialTextTokens.S_ID.value:
        f_row += [char_id]
    sentence = [vocab[r] for r in f_row if 0 < r < n]
  else:
    sentence = [vocab[r] for r in row if 0 < r < n]

  if bpe_used:
    sentence = delim.join(sentence)
    sentence = re.sub("@@ ", "", sentence)
    sentence = sentence.split(delim)

  return sentence


def calculate_bleu(preds, targets):
  """
  :param preds: list of lists
  :param targets: list of lists
  :return: bleu score - float32
  """
  bleu_score = nltk.translate.bleu_score.corpus_bleu(
    targets, preds, emulate_multibleu=True,
  )
  return bleu_score


class BasicText2TextWithAttention(Seq2Seq):
  """
  An example class implementing classical text-to-text model.
  """
  def _create_encoder(self):
    self.params['encoder_params']['src_vocab_size'] = (
      self.data_layer.params['src_vocab_size']
    )
    return super(BasicText2TextWithAttention, self)._create_encoder()

  def _create_decoder(self):
    self.params['decoder_params']['batch_size'] = (
      self.params['batch_size_per_gpu']
    )
    return super(BasicText2TextWithAttention, self)._create_decoder()

  def _create_loss(self):
    self.params['loss_params']['batch_size'] = self.params['batch_size_per_gpu']
    self.params['loss_params']['tgt_vocab_size'] = (
      self.data_layer.params['tgt_vocab_size']
    )
    return super(BasicText2TextWithAttention, self)._create_loss()

  def infer(self, input_values, output_values):
    input_strings, output_strings = [], []
    for input_sample, output_sample in zip(input_values, output_values):
      output_strings.append(text_ids_to_string(
        output_sample[0],
        self.data_layer.params['target_idx2seq'],
        S_ID=self.decoder.params['GO_SYMBOL'],
        EOS_ID=self.decoder.params['END_SYMBOL'],
        PAD_ID=self.decoder.params['PAD_SYMBOL'],
        ignore_special=True, delim=' ',
      ))
      input_strings.append(text_ids_to_string(
        input_sample[0],
        self.data_layer.params['source_idx2seq'],
        S_ID=self.decoder.params['GO_SYMBOL'],
        EOS_ID=self.decoder.params['END_SYMBOL'],
        PAD_ID=self.decoder.params['PAD_SYMBOL'],
        ignore_special=True, delim=' ',
      ))
    return input_strings, output_strings

  def finalize_inference(self, results_per_batch, output_file):
    with codecs.open(output_file, 'w', 'utf-8') as fout:
      step = 0
      for input_strings, output_strings in results_per_batch:
        for input_string, output_string in zip(input_strings, output_strings):
          fout.write(output_string + "\n")
          if step % 200 == 0:
            deco_print("Input sequence:  {}".format(input_string))
            deco_print("Output sequence: {}".format(output_string))
            deco_print("")
          step += 1

  def maybe_print_logs(self, input_values, output_values):
    x, len_x, y, len_y = input_values
    samples = output_values[0]

    x_sample = x[0]
    len_x_sample = len_x[0]
    y_sample = y[0]
    len_y_sample = len_y[0]

    deco_print(
      "Train Source[0]:     " + array_to_string(
        x_sample[:len_x_sample],
        vocab=self.data_layer.params['source_idx2seq'],
        delim=self.data_layer.params["delimiter"],
      ),
      offset=4,
    )
    deco_print(
      "Train Target[0]:     " + array_to_string(
        y_sample[:len_y_sample],
        vocab=self.data_layer.params['target_idx2seq'],
        delim=self.data_layer.params["delimiter"],
      ),
      offset=4,
    )
    deco_print(
      "Train Prediction[0]: " + array_to_string(
        samples[0, :],
        vocab=self.data_layer.params['target_idx2seq'],
        delim=self.data_layer.params["delimiter"],
      ),
      offset=4,
    )
    return {}

  def evaluate(self, input_values, output_values):
    ex, elen_x, ey, elen_y = input_values

    x_sample = ex[0]
    len_x_sample = elen_x[0]
    y_sample = ey[0]
    len_y_sample = elen_y[0]

    deco_print(
      "*****EVAL Source[0]:     " + array_to_string(
        x_sample[:len_x_sample],
        vocab=self.data_layer.params['source_idx2seq'],
        delim=self.data_layer.params["delimiter"],
      ),
      offset=4,
    )
    deco_print(
      "*****EVAL Target[0]:     " + array_to_string(
        y_sample[:len_y_sample],
        vocab=self.data_layer.params['target_idx2seq'],
        delim=self.data_layer.params["delimiter"],
      ),
      offset=4,
    )
    samples = output_values[0]
    deco_print(
      "*****EVAL Prediction[0]: " + array_to_string(
        samples[0, :],
        vocab=self.data_layer.params['target_idx2seq'],
        delim=self.data_layer.params["delimiter"],
      ),
      offset=4,
    )
    preds, targets = [], []

    if self.params.get('eval_using_bleu', True):
      preds.extend([transform_for_bleu(
        sample,
        vocab=self.data_layer.params['target_idx2seq'],
        ignore_special=True,
        delim=self.data_layer.params["delimiter"],
        bpe_used=self.params.get('bpe_used', False),
      ) for sample in samples])
      targets.extend([[transform_for_bleu(
        yi,
        vocab=self.data_layer.params['target_idx2seq'],
        ignore_special=True,
        delim=self.data_layer.params["delimiter"],
        bpe_used=self.params.get('bpe_used', False),
      )] for yi in ey])

    return preds, targets

  def finalize_evaluation(self, results_per_batch):
    preds, targets = [], []
    for preds_cur, targets_cur in results_per_batch:
      if self.params.get('eval_using_bleu', True):
        preds.extend(preds_cur)
        targets.extend(targets_cur)

    if self.params.get('eval_using_bleu', True):
      eval_bleu = calculate_bleu(preds, targets)
      deco_print("Eval BLUE score: {}".format(eval_bleu), offset=4)
      return {'Eval_BLEU_Score': eval_bleu}

    return {}

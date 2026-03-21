package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.io.Reader;

import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_2_2Test {

    @Test
    @Timeout(8000)
    void testRead_withNewLineIncrementsLineCounterAndSetsLastChar() throws IOException {
        Reader reader = new Reader() {
            boolean returnedNewLine = false;

            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                return -1;
            }

            @Override
            public int read() throws IOException {
                if (!returnedNewLine) {
                    returnedNewLine = true;
                    return '\n';
                }
                return -1;
            }

            @Override
            public void close() throws IOException {}
        };
        ExtendedBufferedReader ebr = new ExtendedBufferedReader(reader);

        int result = ebr.read();

        assertEquals('\n', result);
        // lineCounter should be incremented to 1
        int lineNumber = getLineCounter(ebr);
        assertEquals(1, lineNumber);
        int lastChar = getLastChar(ebr);
        assertEquals('\n', lastChar);
    }

    @Test
    @Timeout(8000)
    void testRead_withNonNewLineSetsLastCharButDoesNotIncrementLineCounter() throws IOException {
        Reader reader = new Reader() {
            private int count = 0;

            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                return -1;
            }

            @Override
            public int read() throws IOException {
                if (count == 0) {
                    count++;
                    return 'a';
                }
                return -1;
            }

            @Override
            public void close() throws IOException {}
        };
        ExtendedBufferedReader ebr = new ExtendedBufferedReader(reader);

        int result = ebr.read();

        assertEquals('a', result);
        int lineNumber = getLineCounter(ebr);
        assertEquals(0, lineNumber);
        int lastChar = getLastChar(ebr);
        assertEquals('a', lastChar);
    }

    @Test
    @Timeout(8000)
    void testRead_withEndOfStreamSetsLastCharToEndOfStream() throws IOException {
        Reader reader = new Reader() {

            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                return -1;
            }

            @Override
            public int read() throws IOException {
                return -1;
            }

            @Override
            public void close() throws IOException {}
        };
        ExtendedBufferedReader ebr = new ExtendedBufferedReader(reader);

        int result = ebr.read();

        assertEquals(-1, result);
        int lineNumber = getLineCounter(ebr);
        assertEquals(0, lineNumber);
        int lastChar = getLastChar(ebr);
        assertEquals(-1, lastChar);
    }

    private int getLineCounter(ExtendedBufferedReader ebr) {
        try {
            java.lang.reflect.Field field = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
            field.setAccessible(true);
            return (int) field.get(ebr);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private int getLastChar(ExtendedBufferedReader ebr) {
        try {
            java.lang.reflect.Field field = ExtendedBufferedReader.class.getDeclaredField("lastChar");
            field.setAccessible(true);
            return (int) field.get(ebr);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}
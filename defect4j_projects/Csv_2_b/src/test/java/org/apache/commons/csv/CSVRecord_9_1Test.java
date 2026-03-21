package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Constructor;
import java.util.Collections;
import java.util.Map;

public class CSVRecord_9_1Test {

    @Test
    @Timeout(8000)
    public void testGetCommentReturnsCorrectComment() throws Exception {
        String[] values = new String[] {"value1", "value2"};
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = "This is a comment";
        long recordNumber = 1L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        assertEquals(comment, record.getComment());
    }

    @Test
    @Timeout(8000)
    public void testGetCommentReturnsNullWhenCommentIsNull() throws Exception {
        String[] values = new String[] {"value1", "value2"};
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 1L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        assertNull(record.getComment());
    }
}